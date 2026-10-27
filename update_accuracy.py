"""Courtside NBA prediction accuracy tracker.

Freeze pregame estimates and compare them with actual ESPN logs.
Points and rebounds use upgraded models.
Existing prediction snapshots are preserved.
"""

import csv
import datetime as dt
import math
from collections import defaultdict
from pathlib import Path

UTC = dt.timezone.utc
NOW = dt.datetime.now(UTC)

STATS = (
    "points", "rebounds", "assists",
    "three_pointers", "steals", "blocks"
)

HISTORY = Path("nba_prediction_history.csv")
RESULTS = Path("nba_prediction_results.csv")

HISTORY_FIELDS = [
    "game_key", "game_date", "tipoff_utc", "saved_utc",
    "player_id", "player_name", "team", "opponent",
    "projected_minutes", "position", "baseline_games"
] + [
    f"pred_{s}" for s in STATS
] + [
    f"baseline_{s}" for s in STATS
]

RESULT_FIELDS = HISTORY_FIELDS + [
    "actual_minutes"
] + [
    f"actual_{s}" for s in STATS
] + [
    f"error_{s}" for s in STATS
]


def read(filename):
    with open(filename, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write(filename, fields, rows):
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=fields, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def number(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else 0.0
    except (ValueError, TypeError):
        return 0.0


def clamp(x, minimum, maximum):
    return max(minimum, min(maximum, x))


def norm(value):
    return str(value or "").strip().upper()


def day(value):
    s = str(value or "").strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    if len(s) >= 8 and s[:8].isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return ""


def when(value):
    try:
        d = dt.datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
        if d.tzinfo is None:
            d = d.replace(tzinfo=UTC)
        return d.astimezone(UTC)
    except (ValueError, TypeError):
        return None


def minutes(log):
    return number(
        log.get("minutes")
        or log.get("minutes_played")
        or log.get("minutes_pg")
    )


def is_out(injury):
    return str(injury.get("status", "")).strip().lower() in (
        "out", "inactive", "injured reserve",
        "suspended", "not with team"
    )


def position_group(position):
    p = norm(position)
    if p in ("PG", "SG", "G"):
        return "G"
    if p in ("SF", "PF", "F"):
        return "F"
    if p == "C":
        return "C"
    return ""


def sample_rate(sample, stat, fallback):
    valid = [
        log for log in sample
        if minutes(log) > 0
        and str(log.get(stat, "")).strip() != ""
    ]
    total_minutes = sum(minutes(log) for log in valid)

    if total_minutes <= 0:
        return fallback

    return (
        sum(number(log.get(stat)) for log in valid)
        / total_minutes
    )


def run():
    players = read("nba_stats.csv")
    logs = read("nba_game_logs.csv")
    schedule = read("nba_schedule.csv")
    defense = read("nba_opponent_defense.csv")
    pace_rows = read("nba_team_pace.csv")

    injuries = (
        read("nba_injuries.csv")
        if Path("nba_injuries.csv").exists()
        else []
    )

    history = read(HISTORY) if HISTORY.exists() else []

    pace_by_team = {
        norm(p.get("team")): p
        for p in pace_rows
    }

    by_player = defaultdict(list)

    for log in logs:
        by_player[str(log.get("player_id", ""))].append(log)

    for entries in by_player.values():
        entries.sort(
            key=lambda log: day(log.get("date")),
            reverse=True
        )

    # Weighted league-average defensive statistics.
    defense_averages = defaultdict(
        lambda: [0.0, 0.0]
    )

    for d in defense:
        games = number(d.get("player_games"))
        if games <= 0:
            continue

        for stat in STATS:
            key = (
                d.get("position_type", ""),
                d.get("position", ""),
                stat
            )
            defense_averages[key][0] += (
                games * number(d.get(stat + "_allowed_pg"))
            )
            defense_averages[key][1] += games

    injury_ids = {
        str(i.get("player_id"))
        for i in injuries
        if i.get("player_id") and is_out(i)
    }

    injury_names = {
        (norm(i.get("player_name")), norm(i.get("team")))
        for i in injuries
        if is_out(i)
    }

    def player_is_out(player):
        return (
            str(player.get("player_id", "")) in injury_ids
            or (
                norm(player.get("player_name")),
                norm(player.get("team"))
            ) in injury_names
        )

    def pace_factor(team, opponent):
        a = pace_by_team.get(norm(team))
        b = pace_by_team.get(norm(opponent))

        if not a or not b:
            return 1.0

        own = number(a.get("adjusted_pace"))
        other = number(b.get("adjusted_pace"))

        if own <= 0 or other <= 0:
            return 1.0

        return clamp(
            ((own + other) / 2) / own,
            0.90, 1.10
        )

    def defense_pace_correction(opponent):
        row = pace_by_team.get(norm(opponent))
        if not row:
            return 1.0

        league = number(row.get("league_average_pace"))
        opponent_pace = number(row.get("adjusted_pace"))

        if league <= 0 or opponent_pace <= 0:
            return 1.0

        return clamp(
            league / opponent_pace,
            0.85, 1.15
        )

    def defense_factor(d, stat, opponent):
        if not d:
            return 1.0

        key = (
            d.get("position_type", ""),
            d.get("position", ""),
            stat
        )

        total, appearances = defense_averages[key]

        if appearances <= 0:
            return 1.0

        league_average = total / appearances

        if league_average <= 0:
            return 1.0

        games = number(d.get("player_games"))

        raw = (
            number(d.get(stat + "_allowed_pg"))
            / league_average
        )

        if stat in ("points", "rebounds"):
            raw *= defense_pace_correction(opponent)

        return clamp(
            1 + (games / (games + 20)) * 0.5 * (raw - 1),
            0.85, 1.15
        )

    # Preserve snapshots that have already been saved.
    existing = {
        (r.get("game_key"), r.get("player_id"))
        for r in history
    }

    new_count = 0

    for game in schedule:
        tip = when(game.get("date_utc"))

        # Save estimates only before games begin.
        if tip is None or not (
            NOW < tip <= NOW + dt.timedelta(hours=48)
        ):
            continue

        home = norm(game.get("home"))
        away = norm(game.get("away"))

        if not home or not away:
            continue

        game_date = tip.date().isoformat()
        game_key = f"{tip.isoformat()}|{away}|{home}"

        team_boost = {}

        for team in (home, away):
            roster = [
                p for p in players
                if norm(p.get("team")) == team
                and number(p.get("games_played")) > 0
            ]

            absent_minutes = sum(
                number(p.get("minutes_pg"))
                for p in roster
                if player_is_out(p)
            )

            available = sum(
                1 for p in roster
                if not player_is_out(p)
            )

            team_boost[team] = (
                min(0.08, absent_minutes / 240 * 0.22)
                if available else 0.0
            )

        for player in players:
            team = norm(player.get("team"))

            if team not in (home, away):
                continue

            pid = str(player.get("player_id", ""))

            if not pid or (game_key, pid) in existing:
                continue

            if player_is_out(player):
                continue

            games = number(player.get("games_played"))
            season_minutes = number(
                player.get("minutes_pg")
            )

            if games <= 0 or season_minutes <= 0:
                continue

            opponent = away if team == home else home

            recent = [
                log for log in by_player[pid]
                if day(log.get("date"))
                and day(log.get("date")) < game_date
            ][:10]

            recent_minutes = [
                minutes(log) for log in recent
                if minutes(log) > 0
            ]

            recent_average = (
                sum(recent_minutes) / len(recent_minutes)
                if recent_minutes
                else season_minutes
            )

            projected_minutes = clamp(
                0.75 * season_minutes +
                0.25 * recent_average,
                0, 48
            )

            position = next(
                (
                    log.get("position")
                    for log in recent
                    if log.get("position")
                ),
                ""
            )

            d = next(
                (
                    row for row in defense
                    if norm(row.get("opponent")) == opponent
                    and row.get("position") == position
                    and row.get("position_type") == "position"
                ),
                None
            )

            if d is None:
                pos_group = position_group(position)

                d = next(
                    (
                        row for row in defense
                        if norm(row.get("opponent")) == opponent
                        and row.get("position") == pos_group
                        and row.get("position_type")
                        == "position_group"
                    ),
                    None
                )

            record = {
                "game_key": game_key,
                "game_date": game_date,
                "tipoff_utc": tip.isoformat(),
                "saved_utc": NOW.isoformat(),
                "player_id": pid,
                "player_name": player.get("player_name", ""),
                "team": team,
                "opponent": opponent,
                "projected_minutes": round(
                    projected_minutes, 2
                ),
                "position": position,
                "baseline_games": games
            }

            for stat in STATS:
                baseline = number(
                    player.get(stat + "_pg")
                )
                season_rate = baseline / season_minutes

                last10 = sample_rate(
                    recent[:10], stat, season_rate
                )
                last5 = sample_rate(
                    recent[:5], stat, season_rate
                )

                if stat == "points":
                    # Upgraded points model.
                    rate = (
                        0.55 * season_rate +
                        0.30 * last10 +
                        0.15 * last5
                    )

                elif stat == "rebounds":
                    # NEW: Upgraded rebounds model.
                    rate = (
                        0.50 * season_rate +
                        0.30 * last10 +
                        0.20 * last5
                    )

                else:
                    # Existing models for other statistics.
                    valid = [
                        log for log in recent
                        if minutes(log) > 0
                        and str(log.get(stat, "")).strip()
                    ]

                    weight = games / (games + 12)

                    stabilized = (
                        weight * season_rate +
                        (1 - weight) * last10
                    )

                    recent_weight = (
                        len(valid) / (len(valid) + 10)
                    )

                    rate = (
                        (1 - recent_weight) * stabilized +
                        recent_weight * last10
                    )

                adjustment = defense_factor(
                    d, stat, opponent
                )

                matchup_pace = (
                    pace_factor(team, opponent)
                    if stat in ("points", "rebounds")
                    else 1.0
                )

                prediction = max(
                    0,
                    projected_minutes *
                    rate *
                    adjustment *
                    matchup_pace *
                    (1 + team_boost[team])
                )

                record["pred_" + stat] = round(
                    prediction, 3
                )

                record["baseline_" + stat] = round(
                    baseline, 3
                )

            history.append(record)
            existing.add((game_key, pid))
            new_count += 1

    write(HISTORY, HISTORY_FIELDS, history)

    # Score snapshots using completed game logs.
    # Do not count missing logs or DNPs as zero.
    results = []

    for record in history:
        tip = when(record.get("tipoff_utc"))

        if tip is None or NOW < tip + dt.timedelta(hours=2):
            continue

        candidates = [
            log for log in by_player.get(
                str(record.get("player_id")), []
            )
            if day(log.get("date")) == record["game_date"]
            and norm(log.get("opponent"))
            == norm(record["opponent"])
            and minutes(log) > 0
        ]

        if len(candidates) != 1:
            continue

        actual = candidates[0]

        result = dict(
            record,
            actual_minutes=round(minutes(actual), 2)
        )

        complete = True

        for stat in STATS:
            if str(actual.get(stat, "")).strip() == "":
                complete = False
                break

            value = number(actual.get(stat))

            result["actual_" + stat] = value
            result["error_" + stat] = round(
                abs(
                    number(record.get("pred_" + stat))
                    - value
                ),
                3
            )

        if complete:
            results.append(result)

    write(RESULTS, RESULT_FIELDS, results)

    print(
        f"Prediction snapshots: {len(history)} total, "
        f"{new_count} newly saved; "
        f"scored results: {len(results)}"
    )

    if new_count == 0:
        print(
            "No new eligible pregame games. "
            "Existing prediction history preserved."
        )


if __name__ == "__main__":
    run()
