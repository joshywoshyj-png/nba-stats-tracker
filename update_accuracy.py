
"""Freeze pregame NBA stat estimates and score them against later ESPN game logs.

Runs AFTER update_nba.py and update_schedule.py. CSV snapshots are append-only.
No betting lines, odds, or recommendations.
"""
import csv
import datetime as dt
import math
from collections import defaultdict
from pathlib import Path

UTC = dt.timezone.utc
NOW = dt.datetime.now(UTC)
STATS = ('points', 'rebounds', 'assists', 'three_pointers', 'steals', 'blocks')
HISTORY = Path('nba_prediction_history.csv')
RESULTS = Path('nba_prediction_results.csv')
HISTORY_FIELDS = ['game_key','game_date','tipoff_utc','saved_utc','player_id','player_name','team','opponent','projected_minutes','position','baseline_games'] + [f'pred_{k}' for k in STATS] + [f'baseline_{k}' for k in STATS]
RESULT_FIELDS = HISTORY_FIELDS + ['actual_minutes'] + [f'actual_{k}' for k in STATS] + [f'error_{k}' for k in STATS]


def read(name):
    if not Path(name).exists():
        raise FileNotFoundError(name)
    with open(name, newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def write(name, fields, rows):
    with open(name, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def number(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else 0.0
    except (ValueError, TypeError):
        return 0.0


def day(value):
    s = str(value or '').strip()
    if len(s) >= 10 and s[4] == '-' and s[7] == '-':
        return s[:10]
    if len(s) >= 8 and s[:8].isdigit():
        return s[:4] + '-' + s[4:6] + '-' + s[6:8]
    return ''


def when(value):
    try:
        return dt.datetime.fromisoformat(
            str(value).replace('Z', '+00:00')
        ).astimezone(UTC)
    except (ValueError, TypeError):
        return None


def norm(value):
    return str(value or '').strip().upper()


def minutes(log):
    return number(
        log.get('minutes')
        or log.get('minutes_played')
        or log.get('minutes_pg')
    )


def injury_out(i):
    return str(i.get('status', '')).strip().lower() in (
        'out', 'inactive', 'injured reserve',
        'suspended', 'not with team'
    )


def run():
    players = read('nba_stats.csv')
    logs = read('nba_game_logs.csv')
    schedule = read('nba_schedule.csv')
    defense = read('nba_opponent_defense.csv')
    injuries = (
        read('nba_injuries.csv')
        if Path('nba_injuries.csv').exists()
        else []
    )
    history = read(HISTORY) if HISTORY.exists() else []

    by_player = defaultdict(list)

    for log in logs:
        by_player[str(log.get('player_id', ''))].append(log)

    for entries in by_player.values():
        entries.sort(
            key=lambda x: day(x.get('date')),
            reverse=True
        )

    averages = defaultdict(lambda: [0., 0.])

    for d in defense:
        games = number(d.get('player_games'))
        if not games:
            continue

        for stat in STATS:
            key = (
                d.get('position_type', ''),
                d.get('position', ''),
                stat
            )
            averages[key][0] += (
                games * number(d.get(stat + '_allowed_pg'))
            )
            averages[key][1] += games

    injury_ids = {
        str(i.get('player_id'))
        for i in injuries
        if i.get('player_id') and injury_out(i)
    }

    injury_names = {
        (norm(i.get('player_name')), norm(i.get('team')))
        for i in injuries
        if injury_out(i)
    }

    existing = {
        (r.get('game_key'), r.get('player_id'))
        for r in history
    }

    new = 0

    for game in schedule:
        tip = when(game.get('date_utc'))

        if tip is None or not (
            NOW < tip <= NOW + dt.timedelta(hours=48)
        ):
            continue

        home = norm(game.get('home'))
        away = norm(game.get('away'))

        if not home or not away:
            continue

        date = tip.date().isoformat()
        game_key = f'{tip.isoformat()}|{away}|{home}'

        for p in players:
            team = norm(p.get('team'))

            if team not in (home, away):
                continue

            pid = str(p.get('player_id', ''))

            if not pid or (game_key, pid) in existing:
                continue

            if (
                pid in injury_ids
                or (norm(p.get('player_name')), team) in injury_names
            ):
                continue

            games = number(p.get('games_played'))
            season_min = number(p.get('minutes_pg'))

            if games <= 0 or season_min <= 0:
                continue

            opponent = away if team == home else home

            recent = [
                l for l in by_player[pid]
                if day(l.get('date'))
                and day(l.get('date')) < date
            ][:10]

            recent_mins = [
                minutes(l)
                for l in recent
                if minutes(l) > 0
            ]

            recent_avg = (
                sum(recent_mins) / len(recent_mins)
                if recent_mins else season_min
            )

            projected_min = max(
                0.,
                min(48., .75 * season_min + .25 * recent_avg)
            )

            position = next(
                (
                    l.get('position')
                    for l in recent
                    if l.get('position')
                ),
                ''
            )

            d = next(
                (
                    d for d in defense
                    if norm(d.get('opponent')) == opponent
                    and d.get('position') == position
                    and d.get('position_type') == 'position'
                ),
                None
            )

            if d is None:
                pos_group = {
                    'PG': 'G', 'SG': 'G', 'G': 'G',
                    'SF': 'F', 'PF': 'F', 'F': 'F',
                    'C': 'C'
                }.get(position, '')

                d = next(
                    (
                        d for d in defense
                        if norm(d.get('opponent')) == opponent
                        and d.get('position') == pos_group
                        and d.get('position_type') == 'position_group'
                    ),
                    None
                )

            record = dict(
                game_key=game_key,
                game_date=date,
                tipoff_utc=tip.isoformat(),
                saved_utc=NOW.isoformat(),
                player_id=pid,
                player_name=p.get('player_name', ''),
                team=team,
                opponent=opponent,
                projected_minutes=round(projected_min, 2),
                position=position,
                baseline_games=games
            )

            for stat in STATS:
                baseline = number(p.get(stat + '_pg'))
                season_rate = baseline / season_min

                valid = [
                    l for l in recent
                    if str(l.get(stat, '')).strip()
                    and minutes(l) > 0
                ]

                recent_rate = (
                    sum(number(l.get(stat)) for l in valid)
                    / sum(minutes(l) for l in valid)
                    if valid else season_rate
                )

                weight = games / (games + 12)
                stabilized = (
                    weight * season_rate
                    + (1 - weight) * recent_rate
                )

                recent_weight = len(valid) / (len(valid) + 10)

                rate = (
                    (1 - recent_weight) * stabilized
                    + recent_weight * recent_rate
                )

                factor = 1.

                if d:
                    key_d = (
                        d.get('position_type', ''),
                        d.get('position', ''),
                        stat
                    )

                    total, appearances = averages[key_d]

                    league_avg = (
                        total / appearances
                        if appearances else 0.
                    )

                    if league_avg > 0:
                        dg = number(d.get('player_games'))
                        raw = (
                            number(d.get(stat + '_allowed_pg'))
                            / league_avg
                        )

                        factor = max(
                            .85,
                            min(
                                1.15,
                                1 + (dg / (dg + 20)) * .5 * (raw - 1)
                            )
                        )

                record['pred_' + stat] = round(
                    max(0, projected_min * rate * factor),
                    3
                )
                record['baseline_' + stat] = round(
                    baseline, 3
                )

            history.append(record)
            existing.add((game_key, pid))
            new += 1

    write(HISTORY, HISTORY_FIELDS, history)

    results = []

    for record in history:
        tip = when(record.get('tipoff_utc'))

        if tip is None or NOW < tip + dt.timedelta(hours=2):
            continue

        candidates = [
            l for l in by_player.get(
                str(record['player_id']), []
            )
            if day(l.get('date')) == record['game_date']
            and norm(l.get('opponent')) == norm(record['opponent'])
            and minutes(l) > 0
        ]

        if len(candidates) != 1:
            continue

        actual = candidates[0]

        result = dict(
            record,
            actual_minutes=round(minutes(actual), 2)
        )

        for stat in STATS:
            if str(actual.get(stat, '')).strip() == '':
                break

            value = number(actual.get(stat))
            result['actual_' + stat] = value
            result['error_' + stat] = round(
                abs(number(record.get('pred_' + stat)) - value),
                3
            )
        else:
            results.append(result)

    write(RESULTS, RESULT_FIELDS, results)

    print(
        f'Prediction snapshots: {len(history)} total, '
        f'{new} newly saved; scored results: {len(results)}'
    )

    if new == 0:
        print(
            'No new eligible pregame games in the next 48 hours; '
            'existing history preserved.'
        )


if __name__ == '__main__':
    run()
