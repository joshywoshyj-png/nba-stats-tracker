
"""
COURTSIDE — NBA PREDICTION ACCURACY TRACKER

Upgraded: points, rebounds, assists.

- Preserves existing prediction snapshots
- Saves new predictions only before tipoff
- Matches ESPN logs using local game dates
- Scores finished games with completed player logs
- Does not create historical predictions retroactively
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
    "points",
    "rebounds",
    "assists",
    "three_pointers",
    "steals",
    "blocks",
]

HISTORY_FILE = Path("nba_prediction_history.csv")
RESULTS_FILE = Path("nba_prediction_results.csv")

HISTORY_FIELDS = [
    "game_key",
    "game_date",
    "tipoff_utc",
    "saved_utc",
    "player_id",
    "player_name",
    "team",
    "opponent",
    "projected_minutes",
    "position",
    "baseline_games",
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


def read_csv(path):
    path = Path(path)
    if not path.exists():
        return []

    with path.open(
        "r", newline="", encoding="utf-8-sig"
    ) as file:
        return list(csv.DictReader(file))


def write_csv(path, fields, rows):
    columns = list(fields)

    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)

    with Path(path).open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=columns,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def num(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else 0.0
    except (TypeError, ValueError):
        return 0.0


def clamp(value, low, high):
    return max(low, min(high, value))


def norm(value):
    return str(value or "").strip().upper()


def parse_time(value):
    try:
        parsed = datetime.fromisoformat(
            str(value or "").replace("Z", "+00:00")
        )
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except (TypeError, ValueError):
        return None


def date_value(value):
    value = str(value or "").strip()

    try:
        if len(value) >= 10 and value[4] == "-":
            return datetime.strptime(
                value[:10], "%Y-%m-%d"
            ).date()

        if len(value) >= 8 and value[:8].isdigit():
            return datetime.strptime(
                value[:8], "%Y%m%d"
            ).date()
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


def is_out(injury):
    return norm(injury.get("status")) in {
        "OUT",
        "INACTIVE",
        "INJURED RESERVE",
        "SUSPENDED",
        "NOT WITH TEAM",
    }


def position_group(position):
    position = norm(position)

    if position in {"PG", "SG", "G"}:
        return "G"
    if position in {"SF", "PF", "F"}:
        return "F"
    if position == "C":
        return "C"

    return ""


def sample_rate(logs, stat, fallback):
    valid = [
        log for log in logs
        if minutes(log) > 0
        and str(log.get(stat, "")).strip() != ""
    ]

    total_minutes = sum(minutes(log) for log in valid)

    if total_minutes <= 0:
        return fallback

    return (
        sum(num(log.get(stat)) for log in valid)
        / total_minutes
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
    print("Logs:", len(logs))
    print("Schedule:", len(schedule))
    print("Existing predictions:", len(history))

    logs_by_player = defaultdict(list)

    for log in logs:
        pid = str(log.get("player_id", ""))
        if pid:
            logs_by_player[pid].append(log)

    for entries in logs_by_player.values():
        entries.sort(
            key=lambda log: (
                date_value(log.get("date"))
                or datetime.min.date()
            ),
            reverse=True,
        )

    pace_by_team = {
        norm(row.get("team")): row
        for row in pace
    }

    defensive_baselines = defaultdict(
        lambda: [0.0, 0.0]
    )

    for row in defense:
        games = num(row.get("player_games"))
        if games <= 0:
            continue

        for stat in STATS:
            key = (
                row.get("position_type", ""),
                row.get("position", ""),
                stat,
            )
            baseline = defensive_baselines[key]

            baseline[0] += (
                games * num(row.get(stat + "_allowed_pg"))
            )
            baseline[1] += games

    def pace_factor(team, opponent):
        own = pace_by_team.get(norm(team))
        other = pace_by_team.get(norm(opponent))

        if not own or not other:
            return 1.0

        own_pace = num(own.get("adjusted_pace"))
        other_pace = num(other.get("adjusted_pace"))

        if own_pace <= 0 or other_pace <= 0:
            return 1.0

        return clamp(
            ((own_pace + other_pace) / 2) / own_pace,
            0.90,
            1.10,
        )

    def defense_pace_correction(opponent):
        row = pace_by_team.get(norm(opponent))
        if not row:
            return 1.0

        league = num(row.get("league_average_pace"))
        opponent_pace = num(row.get("adjusted_pace"))

        if league <= 0 or opponent_pace <= 0:
            return 1.0

        return clamp(
            league / opponent_pace,
            0.85,
            1.15,
        )

    def defense_factor(row, stat, opponent):
        if not row:
            return 1.0

        key = (
            row.get("position_type", ""),
            row.get("position", ""),
            stat,
        )

        total, games = defensive_baselines[key]

        if games <= 0:
            return 1.0

        league_average = total / games

        if league_average <= 0:
            return 1.0

        raw = (
            num(row.get(stat + "_allowed_pg"))
            / league_average
        )

        # Pace-neutralize defense for upgraded stats.
        if stat in ("points", "rebounds", "assists"):
            raw *= defense_pace_correction(opponent)

        sample = num(row.get("player_games"))

        return clamp(
            1 + (sample / (sample + 20)) * 0.5 * (raw - 1),
            0.85,
            1.15,
        )

    out_ids = set()
    out_names = set()

    for injury in injuries:
        if not is_out(injury):
            continue

        if injury.get("player_id"):
            out_ids.add(str(injury["player_id"]))

        out_names.add((
            norm(injury.get("player_name")),
            norm(injury.get("team")),
        ))

    def player_is_out(player):
        return (
            str(player.get("player_id", "")) in out_ids
            or (
                norm(player.get("player_name")),
                norm(player.get("team")),
            ) in out_names
        )

    existing = {
        (
            row.get("game_key"),
            str(row.get("player_id", "")),
        )
        for row in history
    }

    new_snapshots = 0

    # --------------------------------------------------------
    # CREATE PREGAME PREDICTIONS
    # --------------------------------------------------------

    for game in schedule:
        tip = parse_time(game.get("date_utc"))

        if tip is None:
            continue

        if not (
            NOW < tip <= NOW + timedelta(hours=48)
        ):
            continue

        home = norm(game.get("home"))
        away = norm(game.get("away"))

        if not home or not away:
            continue

        game_day = local_date(tip)

        game_key = (
            f"{tip.isoformat()}|{away}|{home}"
        )

        injury_boosts = {}

        for team in (home, away):
            roster = [
                player for player in players
                if norm(player.get("team")) == team
                and num(player.get("games_played")) > 0
            ]

            absent_minutes = sum(
                num(player.get("minutes_pg"))
                for player in roster
                if player_is_out(player)
            )

            available = sum(
                1 for player in roster
                if not player_is_out(player)
            )

            injury_boosts[team] = (
                min(
                    0.08,
                    absent_minutes / 240 * 0.22,
                )
                if available else 0.0
            )

        for player in players:
            team = norm(player.get("team"))

            if team not in (home, away):
                continue

            pid = str(player.get("player_id", ""))

            if not pid:
                continue

            key = (game_key, pid)

            if key in existing or player_is_out(player):
                continue

            games = num(player.get("games_played"))
            season_minutes = num(
                player.get("minutes_pg")
            )

            if games <= 0 or season_minutes <= 0:
                continue

            opponent = away if team == home else home

            recent = [
                log for log in logs_by_player[pid]
                if date_value(log.get("date"))
                and date_value(log.get("date")) < game_day
            ][:10]

            recent_minutes = [
                minutes(log)
                for log in recent
                if minutes(log) > 0
            ]

            recent_average = (
                sum(recent_minutes) / len(recent_minutes)
                if recent_minutes
                else season_minutes
            )

            projected_minutes = clamp(
                0.75 * season_minutes
                + 0.25 * recent_average,
                0,
                48,
            )

            position = next(
                (
                    log.get("position")
                    for log in recent
                    if log.get("position")
                ),
                "",
            )

            defense_row = next(
                (
                    row for row in defense
                    if norm(row.get("opponent")) == opponent
                    and norm(row.get("position"))
                    == norm(position)
                    and row.get("position_type") == "position"
                ),
                None,
            )

            if defense_row is None:
                grouped = position_group(position)

                defense_row = next(
                    (
                        row for row in defense
                        if norm(row.get("opponent")) == opponent
                        and norm(row.get("position"))
                        == grouped
                        and row.get("position_type")
                        == "position_group"
                    ),
                    None,
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
                "projected_minutes": round(
                    projected_minutes, 2
                ),
                "position": position,
                "baseline_games": games,
            }

            for stat in STATS:
                baseline = num(
                    player.get(stat + "_pg")
                )

                season_rate = (
                    baseline / season_minutes
                )

                last10 = sample_rate(
                    recent[:10], stat, season_rate
                )
                last5 = sample_rate(
                    recent[:5], stat, season_rate
                )

                if stat == "points":
                    rate = (
                        0.55 * season_rate
                        + 0.30 * last10
                        + 0.15 * last5
                    )

                elif stat == "rebounds":
                    rate = (
                        0.50 * season_rate
                        + 0.30 * last10
                        + 0.20 * last5
                    )

                elif stat == "assists":
                    # NEW: Upgraded assists model.
                    rate = (
                        0.45 * season_rate
                        + 0.35 * last10
                        + 0.20 * last5
                    )

                else:
                    valid = [
                        log for log in recent
                        if minutes(log) > 0
                        and str(log.get(stat, "")).strip()
                    ]

                    season_weight = (
                        games / (games + 12)
                    )

                    stabilized = (
                        season_weight * season_rate
                        + (1 - season_weight) * last10
                    )

                    recent_weight = (
                        len(valid) / (len(valid) + 10)
                    )

                    rate = (
                        (1 - recent_weight) * stabilized
                        + recent_weight * last10
                    )

                matchup_pace = (
                    pace_factor(team, opponent)
                    if stat in (
                        "points", "rebounds", "assists"
                    )
                    else 1.0
                )

                prediction = max(
                    0,
                    projected_minutes
                    * rate
                    * defense_factor(
                        defense_row,
                        stat,
                        opponent,
                    )
                    * matchup_pace
                    * (1 + injury_boosts[team]),
                )

                record["pred_" + stat] = round(
                    prediction, 3
                )

                record["baseline_" + stat] = round(
                    baseline, 3
                )

            history.append(record)
            existing.add(key)
            new_snapshots += 1

    write_csv(
        HISTORY_FILE,
        HISTORY_FIELDS,
        history,
    )

    # --------------------------------------------------------
    # SCORE COMPLETED GAMES
    # --------------------------------------------------------

    results = []

    matched = 0
    no_log = 0
    incomplete = 0
    not_finished = 0
    invalid_snapshot = 0

    for record in history:
        tip = parse_time(record.get("tipoff_utc"))

        if tip is None:
            continue

        saved = parse_time(record.get("saved_utc"))

        # Only genuine pregame snapshots can be scored.
        if saved is not None and saved >= tip:
            invalid_snapshot += 1
            continue

        if NOW < tip + timedelta(hours=2):
            not_finished += 1
            continue

        pid = str(record.get("player_id", ""))
        opponent = norm(record.get("opponent"))
        game_day = local_date(tip)

        acceptable_dates = {
            game_day - timedelta(days=1),
            game_day,
            game_day + timedelta(days=1),
        }

        candidates = []

        for log in logs_by_player.get(pid, []):
            log_day = date_value(log.get("date"))

            if log_day not in acceptable_dates:
                continue

            if norm(log.get("opponent")) != opponent:
                continue

            if minutes(log) <= 0:
                continue

            candidates.append(log)

        if not candidates:
            no_log += 1
            continue

        candidates.sort(
            key=lambda log: abs(
                (
                    date_value(log.get("date"))
                    - game_day
                ).days
            )
        )

        if len(candidates) > 1:
            first_distance = abs(
                (
                    date_value(candidates[0].get("date"))
                    - game_day
                ).days
            )
            second_distance = abs(
                (
                    date_value(candidates[1].get("date"))
                    - game_day
                ).days
            )

            if first_distance == second_distance:
                no_log += 1
                continue

        actual = candidates[0]

        if any(
            str(actual.get(stat, "")).strip() == ""
            for stat in STATS
        ):
            incomplete += 1
            continue

        result = dict(record)
        result["actual_minutes"] = round(
            minutes(actual), 2
        )

        for stat in STATS:
            actual_value = num(actual.get(stat))
            predicted_value = num(
                record.get("pred_" + stat)
            )

            result["actual_" + stat] = actual_value
            result["error_" + stat] = round(
                abs(predicted_value - actual_value),
                3,
            )

        results.append(result)
        matched += 1

    write_csv(
        RESULTS_FILE,
        RESULT_FIELDS,
        results,
    )

    print()
    print("=" * 55)
    print("COURTSIDE ACCURACY RESULTS")
    print("=" * 55)

    print("Saved predictions:", len(history))
    print("New pregame predictions:", new_snapshots)
    print("Scored results:", matched)
    print("Waiting for logs:", no_log)
    print("Incomplete box scores:", incomplete)
    print("Games not ready:", not_finished)
    print("Late snapshots excluded:", invalid_snapshot)

    if results:
        print()
        print("MEAN ABSOLUTE ERROR")

        for stat in STATS:
            errors = [
                num(row.get("error_" + stat))
                for row in results
            ]

            mae = sum(errors) / len(errors)
            print(f"{stat}: {mae:.2f}")

    print()
    print("History file:", HISTORY_FILE)
    print("Results file:", RESULTS_FILE)


if __name__ == "__main__":
    main()
