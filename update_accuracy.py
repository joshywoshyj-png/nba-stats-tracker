
"""
COURTSIDE NBA PREDICTION ACCURACY
Upgraded PTS, REB, AST and 3PM models.
Only pregame snapshots are scored.
"""

import csv
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

UTC = timezone.utc
CHICAGO = ZoneInfo("America/Chicago")
NOW = datetime.now(UTC)

STATS = [
    "points", "rebounds", "assists",
    "three_pointers", "steals", "blocks",
]

HISTORY_FILE = Path("nba_prediction_history.csv")
RESULTS_FILE = Path("nba_prediction_results.csv")

HISTORY_FIELDS = [
    "game_key", "game_date", "tipoff_utc", "saved_utc",
    "player_id", "player_name", "team", "opponent",
    "projected_minutes", "position", "baseline_games",
] + [f"pred_{s}" for s in STATS] + [
    f"baseline_{s}" for s in STATS
]

RESULT_FIELDS = HISTORY_FIELDS + [
    "actual_minutes"
] + [f"actual_{s}" for s in STATS] + [
    f"error_{s}" for s in STATS
]

ATTEMPT_COLUMNS = [
    "three_pointers_attempted",
    "three_point_attempts",
    "three_point_attempted",
    "three_pointers_attempts",
    "three_point_attempts_pg",
    "three_pointers_attempted_pg",
    "three_pa", "three_pa_pg",
    "three_point_attempts_per_game",
    "three_pointers_attempted_per_game",
    "fg3a", "fg3a_pg", "3pa", "3pa_pg",
]


def read_csv(path):
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path, fields, rows):
    columns = list(fields)
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=columns, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def num(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else 0.0
    except (TypeError, ValueError):
        return 0.0


def norm(value):
    return str(value or "").strip().upper()


def clamp(value, low, high):
    return max(low, min(high, value))


def parse_time(value):
    try:
        d = datetime.fromisoformat(
            str(value or "").replace("Z", "+00:00")
        )
        if d.tzinfo is None:
            d = d.replace(tzinfo=UTC)
        return d.astimezone(UTC)
    except (ValueError, TypeError):
        return None


def date_value(value):
    value = str(value or "").strip()
    try:
        if len(value) >= 10 and value[4] == "-":
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        if len(value) >= 8 and value[:8].isdigit():
            return datetime.strptime(value[:8], "%Y%m%d").date()
    except ValueError:
        pass
    return None


def local_date(tip):
    return tip.astimezone(CHICAGO).date()


def minutes(log):
    return num(
        log.get("minutes")
        or log.get("minutes_played")
        or log.get("minutes_pg")
    )


def attempts(row):
    for key in ATTEMPT_COLUMNS:
        if key in row and str(row[key] or "").strip() != "":
            return num(row[key])
    return None


def position_group(position):
    p = norm(position)
    if p in ("PG", "SG", "G"):
        return "G"
    if p in ("SF", "PF", "F"):
        return "F"
    return "C" if p == "C" else ""


def sample_rate(logs, stat, fallback):
    valid = [
        l for l in logs
        if minutes(l) > 0
        and str(l.get(stat, "")).strip() != ""
    ]
    total_minutes = sum(minutes(l) for l in valid)
    if total_minutes <= 0:
        return fallback
    return sum(num(l.get(stat)) for l in valid) / total_minutes


def three_prediction(
    player, recent, projected_minutes,
    defense_factor, pace_factor, injury_boost
):
    season_minutes = num(player.get("minutes_pg"))
    season_makes = num(player.get("three_pointers_pg"))
    season_attempts = attempts(player)

    def fallback():
        season_rate = (
            season_makes / season_minutes
            if season_minutes > 0 else 0
        )
        last10 = sample_rate(
            recent[:10], "three_pointers", season_rate
        )
        valid = [
            l for l in recent
            if minutes(l) > 0
            and str(l.get("three_pointers", "")).strip() != ""
        ]
        games = num(player.get("games_played"))
        season_weight = games / (games + 12)
        stabilized = (
            season_weight * season_rate
            + (1 - season_weight) * last10
        )
        recent_weight = len(valid) / (len(valid) + 10)
        rate = (
            (1 - recent_weight) * stabilized
            + recent_weight * last10
        )
        return (
            projected_minutes * rate
            * defense_factor * pace_factor
            * (1 + injury_boost)
        )

    if (
        season_attempts is None
        or season_attempts <= 0
        or season_minutes <= 0
    ):
        return max(0, fallback())

    available = [
        l for l in recent
        if minutes(l) > 0 and attempts(l) is not None
    ]
    if not available:
        return max(0, fallback())

    season_attempt_rate = season_attempts / season_minutes

    def attempt_rate(logs, default):
        valid = [
            l for l in logs
            if minutes(l) > 0 and attempts(l) is not None
        ]
        total_minutes = sum(minutes(l) for l in valid)
        if total_minutes <= 0:
            return default
        return sum(attempts(l) for l in valid) / total_minutes

    last10 = attempt_rate(recent[:10], season_attempt_rate)
    last5 = attempt_rate(recent[:5], season_attempt_rate)

    projected_attempts = projected_minutes * (
        0.50 * season_attempt_rate
        + 0.30 * last10
        + 0.20 * last5
    )

    season_pct = clamp(
        season_makes / season_attempts, 0, 1
    )

    recent_valid = [
        l for l in recent[:10]
        if minutes(l) > 0
        and attempts(l) is not None
        and str(l.get("three_pointers", "")).strip() != ""
    ]

    recent_attempts = sum(attempts(l) for l in recent_valid)
    recent_makes = sum(
        num(l.get("three_pointers")) for l in recent_valid
    )

    # Shrink recent shooting toward season shooting percentage.
    expected_pct = clamp(
        (recent_makes + 60 * season_pct)
        / (recent_attempts + 60),
        0, 1
    )

    return max(
        0,
        projected_attempts * expected_pct
        * defense_factor * pace_factor
        * (1 + injury_boost)
    )


def main():
    players = read_csv("nba_stats.csv")
    logs = read_csv("nba_game_logs.csv")
    schedule = read_csv("nba_schedule.csv")
    defense = read_csv("nba_opponent_defense.csv")
    pace = read_csv("nba_team_pace.csv")
    injuries = read_csv("nba_injuries.csv")
    history = read_csv(HISTORY_FILE)

    print("COURTSIDE ACCURACY UPDATE")
    print("Players:", len(players))
    print("Game logs:", len(logs))
    print("Schedule games:", len(schedule))
    print("Saved predictions:", len(history))

    logs_by_player = defaultdict(list)
    for log in logs:
        pid = str(log.get("player_id", ""))
        if pid:
            logs_by_player[pid].append(log)

    for entries in logs_by_player.values():
        entries.sort(
            key=lambda l: (
                date_value(l.get("date"))
                or datetime.min.date()
            ),
            reverse=True
        )

    pace_map = {
        norm(row.get("team")): row for row in pace
    }

    defense_baselines = defaultdict(lambda: [0.0, 0.0])
    for row in defense:
        games = num(row.get("player_games"))
        if games <= 0:
            continue
        for stat in STATS:
            key = (
                row.get("position_type", ""),
                row.get("position", ""),
                stat
            )
            b = defense_baselines[key]
            b[0] += games * num(row.get(stat + "_allowed_pg"))
            b[1] += games

    def pace_factor(team, opponent):
        own = pace_map.get(norm(team))
        other = pace_map.get(norm(opponent))
        if not own or not other:
            return 1.0
        a = num(own.get("adjusted_pace"))
        b = num(other.get("adjusted_pace"))
        return (
            clamp(((a + b) / 2) / a, .9, 1.1)
            if a > 0 and b > 0 else 1.0
        )

    def defense_pace(opponent):
        row = pace_map.get(norm(opponent))
        if not row:
            return 1.0
        league = num(row.get("league_average_pace"))
        opponent_pace = num(row.get("adjusted_pace"))
        return (
            clamp(league / opponent_pace, .85, 1.15)
            if league > 0 and opponent_pace > 0 else 1.0
        )

    def defense_factor(row, stat, opponent):
        if not row:
            return 1.0
        key = (
            row.get("position_type", ""),
            row.get("position", ""),
            stat
        )
        total, games = defense_baselines[key]
        if games <= 0 or total <= 0:
            return 1.0

        raw = (
            num(row.get(stat + "_allowed_pg"))
            / (total / games)
        )
        if stat in ("points", "rebounds", "assists"):
            raw *= defense_pace(opponent)

        sample = num(row.get("player_games"))
        return clamp(
            1 + (sample / (sample + 20)) * .5 * (raw - 1),
            .85, 1.15
        )

    out_ids = set()
    out_names = set()
    for injury in injuries:
        if norm(injury.get("status")) not in {
            "OUT", "INACTIVE", "INJURED RESERVE",
            "SUSPENDED", "NOT WITH TEAM"
        }:
            continue
        if injury.get("player_id"):
            out_ids.add(str(injury["player_id"]))
        out_names.add((
            norm(injury.get("player_name")),
            norm(injury.get("team"))
        ))

    def is_out(player):
        return (
            str(player.get("player_id", "")) in out_ids
            or (
                norm(player.get("player_name")),
                norm(player.get("team"))
            ) in out_names
        )

    existing = {
        (r.get("game_key"), str(r.get("player_id", "")))
        for r in history
    }

    new_snapshots = 0

    # Save only future pregame predictions.
    for game in schedule:
        tip = parse_time(game.get("date_utc"))
        if tip is None or not (
            NOW < tip <= NOW + timedelta(hours=48)
        ):
            continue

        home = norm(game.get("home"))
        away = norm(game.get("away"))
        if not home or not away:
            continue

        game_day = local_date(tip)
        game_key = f"{tip.isoformat()}|{away}|{home}"

        boosts = {}
        for team in (home, away):
            roster = [
                p for p in players
                if norm(p.get("team")) == team
                and num(p.get("games_played")) > 0
            ]
            absent_minutes = sum(
                num(p.get("minutes_pg"))
                for p in roster if is_out(p)
            )
            available = any(not is_out(p) for p in roster)
            boosts[team] = (
                min(.08, absent_minutes / 240 * .22)
                if available else 0
            )

        for player in players:
            team = norm(player.get("team"))
            if team not in (home, away):
                continue

            pid = str(player.get("player_id", ""))
            if not pid or is_out(player):
                continue

            if (game_key, pid) in existing:
                continue

            games = num(player.get("games_played"))
            season_minutes = num(player.get("minutes_pg"))
            if games <= 0 or season_minutes <= 0:
                continue

            opponent = away if team == home else home

            recent = [
                l for l in logs_by_player[pid]
                if date_value(l.get("date"))
                and date_value(l.get("date")) < game_day
            ][:10]

            played_minutes = [
                minutes(l) for l in recent if minutes(l) > 0
            ]
            recent_average = (
                sum(played_minutes) / len(played_minutes)
                if played_minutes else season_minutes
            )
            projected_minutes = clamp(
                .75 * season_minutes + .25 * recent_average,
                0, 48
            )

            position = next(
                (l.get("position") for l in recent
                 if l.get("position")), ""
            )

            defense_row = next(
                (
                    d for d in defense
                    if norm(d.get("opponent")) == opponent
                    and norm(d.get("position")) == norm(position)
                    and d.get("position_type") == "position"
                ),
                None
            )
            if defense_row is None:
                grouped = position_group(position)
                defense_row = next(
                    (
                        d for d in defense
                        if norm(d.get("opponent")) == opponent
                        and norm(d.get("position")) == grouped
                        and d.get("position_type") == "position_group"
                    ),
                    None
                )

            record = {
                "game_key": game_key,
                "game_date": game_day.isoformat(),
                "tipoff_utc": tip.isoformat(),
                "saved_utc": NOW.isoformat(),
                "player_id": pid,
                "player_name": player.get("player_name", ""),
                "team": team,
                "opponent": opponent,
                "projected_minutes": round(projected_minutes, 2),
                "position": position,
                "baseline_games": games
            }

            for stat in STATS:
                baseline = num(player.get(stat + "_pg"))
                season_rate = baseline / season_minutes
                last10 = sample_rate(
                    recent[:10], stat, season_rate
                )
                last5 = sample_rate(
                    recent[:5], stat, season_rate
                )

                df = defense_factor(
                    defense_row, stat, opponent
                )
                pf = pace_factor(team, opponent)

                if stat == "three_pointers":
                    prediction = three_prediction(
                        player, recent, projected_minutes,
                        df, pf, boosts[team]
                    )
                else:
                    if stat == "points":
                        rate = (
                            .55 * season_rate
                            + .30 * last10
                            + .15 * last5
                        )
                    elif stat == "rebounds":
                        rate = (
                            .50 * season_rate
                            + .30 * last10
                            + .20 * last5
                        )
                    elif stat == "assists":
                        rate = (
                            .45 * season_rate
                            + .35 * last10
                            + .20 * last5
                        )
                    else:
                        valid = [
                            l for l in recent
                            if minutes(l) > 0
                            and str(l.get(stat, "")).strip() != ""
                        ]
                        sw = games / (games + 12)
                        stable = (
                            sw * season_rate
                            + (1 - sw) * last10
                        )
                        rw = len(valid) / (len(valid) + 10)
                        rate = (
                            (1 - rw) * stable
                            + rw * last10
                        )

                    pace_adjustment = (
                        pf if stat in (
                            "points", "rebounds", "assists"
                        ) else 1.0
                    )
                    prediction = max(
                        0,
                        projected_minutes * rate * df
                        * pace_adjustment
                        * (1 + boosts[team])
                    )

                record["pred_" + stat] = round(
                    prediction, 3
                )
                record["baseline_" + stat] = round(
                    baseline, 3
                )

            history.append(record)
            existing.add((game_key, pid))
            new_snapshots += 1

    write_csv(HISTORY_FILE, HISTORY_FIELDS, history)

    # Match saved predictions to completed player logs.
    results = []
    matched = 0
    missing_logs = 0
    incomplete = 0
    waiting = 0
    invalid = 0

    for record in history:
        tip = parse_time(record.get("tipoff_utc"))
        if tip is None:
            continue

        saved = parse_time(record.get("saved_utc"))
        if saved is not None and saved >= tip:
            invalid += 1
            continue

        if NOW < tip + timedelta(hours=2):
            waiting += 1
            continue

        pid = str(record.get("player_id", ""))
        opponent = norm(record.get("opponent"))
        game_day = local_date(tip)

        valid_dates = {
            game_day - timedelta(days=1),
            game_day,
            game_day + timedelta(days=1)
        }

        candidates = [
            l for l in logs_by_player.get(pid, [])
            if date_value(l.get("date")) in valid_dates
            and norm(l.get("opponent")) == opponent
            and minutes(l) > 0
        ]

        if not candidates:
            missing_logs += 1
            continue

        candidates.sort(
            key=lambda l: abs(
                (date_value(l.get("date")) - game_day).days
            )
        )

        if len(candidates) > 1:
            first = abs(
                (date_value(candidates[0].get("date")) - game_day).days
            )
            second = abs(
                (date_value(candidates[1].get("date")) - game_day).days
            )
            if first == second:
                missing_logs += 1
                continue

        actual = candidates[0]

        if any(
            str(actual.get(stat, "")).strip() == ""
            for stat in STATS
        ):
            incomplete += 1
            continue

        result = dict(record)
        result["actual_minutes"] = round(minutes(actual), 2)

        for stat in STATS:
            actual_value = num(actual.get(stat))
            predicted_value = num(
                record.get("pred_" + stat)
            )
            result["actual_" + stat] = actual_value
            result["error_" + stat] = round(
                abs(predicted_value - actual_value), 3
            )

        results.append(result)
        matched += 1

    write_csv(RESULTS_FILE, RESULT_FIELDS, results)

    print()
    print("COURTSIDE ACCURACY RESULTS")
    print("-------------------------")
    print("Saved predictions:", len(history))
    print("New pregame predictions:", new_snapshots)
    print("Scored results:", matched)
    print("Waiting for logs:", missing_logs)
    print("Incomplete box scores:", incomplete)
    print("Games not ready:", waiting)
    print("Late snapshots excluded:", invalid)

    if results:
        print()
        print("MEAN ABSOLUTE ERROR")
        for stat in STATS:
            errors = [
                num(row.get("error_" + stat))
                for row in results
            ]
            print(
                f"{stat}: {sum(errors)/len(errors):.2f}"
            )


if __name__ == "__main__":
    main()
