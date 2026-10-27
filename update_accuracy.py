
"""Save pregame NBA predictions and compare them with actual results."""

import csv
import datetime as dt
import math
from collections import defaultdict
from pathlib import Path

UTC = dt.timezone.utc
NOW = dt.datetime.now(UTC)

STATS = (
    "points",
    "rebounds",
    "assists",
    "three_pointers",
    "steals",
    "blocks",
)

HISTORY = Path("nba_prediction_history.csv")
RESULTS = Path("nba_prediction_results.csv")

HISTORY_FIELDS = [
    "game_key", "game_date", "tipoff_utc", "saved_utc",
    "player_id", "player_name", "team", "opponent",
    "projected_minutes", "position", "baseline_games",
] + [
    f"pred_{stat}" for stat in STATS
] + [
    f"baseline_{stat}" for stat in STATS
]

RESULT_FIELDS = HISTORY_FIELDS + [
    "actual_minutes"
] + [
    f"actual_{stat}" for stat in STATS
] + [
    f"error_{stat}" for stat in STATS
]


def read(name):
    if not Path(name).exists():
        raise FileNotFoundError(name)

    with open(name, newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def write(name, fields, rows):
    with open(name, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fields,
            extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else 0.0
    except (ValueError, TypeError):
        return 0.0


def day(value):
    value = str(value or "").strip()

    if len(value) >= 10 and value[4] == "-" and value[7] == "-":
        return value[:10]

    if len(value) >= 8 and value[:8].isdigit():
        return (
            value[:4] + "-" +
            value[4:6] + "-" +
            value[6:8]
        )

    return ""


def when(value):
    try:
        return dt.datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        ).astimezone(UTC)
    except (ValueError, TypeError):
        return None


def norm(value):
    return str(value or "").strip().upper()


def minutes(log):
    return number(
        log.get("minutes")
        or log.get("minutes_played")
        or log.get("minutes_pg")
    )


def injury_out(injury):
    return str(
        injury.get("status", "")
    ).strip().lower() in (
        "out",
        "inactive",
        "injured reserve",
        "suspended",
        "not with team",
    )


def run():
    players = read("nba_stats.csv")
    logs = read("nba_game_logs.csv")
    schedule = read("nba_schedule.csv")
    defense = read("nba_opponent_defense.csv")

    injuries = (
        read("nba_injuries.csv")
        if Path("nba_injuries.csv").exists()
        else []
    )

    history = (
        read(HISTORY)
        if HISTORY.exists()
        else []
    )

    by_player = defaultdict(list)

    for log in logs:
        player_id = str(log.get("player_id", ""))
        by_player[player_id].append(log)

    for entries in by_player.values():
        entries.sort(
            key=lambda log: day(log.get("date")),
            reverse=True
        )

    # Calculate league-wide defensive averages
    # for each position and stat.

    averages = defaultdict(lambda: [0.0, 0.0])

    for entry in defense:
        games = number(entry.get("player_games"))

        if games <= 0:
            continue

        for stat in STATS:
            key = (
                entry.get("position_type", ""),
                entry.get("position", ""),
                stat,
            )

            averages[key][0] += (
                games * number(entry.get(stat + "_allowed_pg"))
            )

            averages[key][1] += games

    # Identify unavailable players.

    injury_ids = {
        str(injury.get("player_id"))
        for injury in injuries
        if injury.get("player_id") and injury_out(injury)
    }

    injury_names = {
        (
            norm(injury.get("player_name")),
            norm(injury.get("team")),
        )
        for injury in injuries
        if injury_out(injury)
    }

    # Calculate the same teammate injury boost
    # used by courtside_schedule_widget.js.

    team_players = defaultdict(list)

    for player in players:
        if number(player.get("games_played")) > 0:
            team_players[norm(player.get("team"))].append(player)

    team_boosts = {}

    for team, roster in team_players.items():
        absent = [
            player
            for player in roster
            if (
                str(player.get("player_id", "")) in injury_ids
                or (
                    norm(player.get("player_name")),
                    team,
                ) in injury_names
            )
        ]

        absent_minutes = sum(
            number(player.get("minutes_pg"))
            for player in absent
        )

        available_count = len(roster) - len(absent)

        team_boosts[team] = (
            min(0.08, absent_minutes / 240 * 0.22)
            if available_count > 0
            else 0.0
        )

    existing = {
        (row.get("game_key"), row.get("player_id"))
        for row in history
    }

    new_predictions = 0

    # Save predictions for games starting
    # within the next 48 hours.

    for game in schedule:
        tipoff = when(game.get("date_utc"))

        if tipoff is None:
            continue

        if not (
            NOW < tipoff <= NOW + dt.timedelta(hours=48)
        ):
            continue

        home = norm(game.get("home"))
        away = norm(game.get("away"))

        if not home or not away:
            continue

        game_date = tipoff.date().isoformat()

        game_key = (
            f"{tipoff.isoformat()}|{away}|{home}"
        )

        for player in players:
            team = norm(player.get("team"))

            if team not in (home, away):
                continue

            player_id = str(player.get("player_id", ""))

            if not player_id:
                continue

            if (game_key, player_id) in existing:
                continue

            if (
                player_id in injury_ids
                or (
                    norm(player.get("player_name")),
                    team,
                ) in injury_names
            ):
                continue

            games_played = number(
                player.get("games_played")
            )

            season_minutes = number(
                player.get("minutes_pg")
            )

            if games_played <= 0 or season_minutes <= 0:
                continue

            opponent = away if team == home else home

            recent = [
                log
                for log in by_player[player_id]
                if (
                    day(log.get("date"))
                    and day(log.get("date")) < game_date
                )
            ][:10]

            recent_minutes = [
                minutes(log)
                for log in recent
                if minutes(log) > 0
            ]

            recent_average_minutes = (
                sum(recent_minutes) / len(recent_minutes)
                if recent_minutes
                else season_minutes
            )

            projected_minutes = max(
                0.0,
                min(
                    48.0,
                    0.75 * season_minutes
                    + 0.25 * recent_average_minutes,
                ),
            )

            position = next(
                (
                    log.get("position")
                    for log in recent
                    if log.get("position")
                ),
                "",
            )

            # Find opponent defense against the
            # player's position.

            opponent_defense = next(
                (
                    entry
                    for entry in defense
                    if (
                        norm(entry.get("opponent")) == opponent
                        and entry.get("position") == position
                        and entry.get("position_type")
                        == "position"
                    )
                ),
                None,
            )

            if opponent_defense is None:
                position_group = {
                    "PG": "G",
                    "SG": "G",
                    "G": "G",
                    "SF": "F",
                    "PF": "F",
                    "F": "F",
                    "C": "C",
                }.get(position, "")

                opponent_defense = next(
                    (
                        entry
                        for entry in defense
                        if (
                            norm(entry.get("opponent"))
                            == opponent
                            and entry.get("position")
                            == position_group
                            and entry.get("position_type")
                            == "position_group"
                        )
                    ),
                    None,
                )

            record = {
                "game_key": game_key,
                "game_date": game_date,
                "tipoff_utc": tipoff.isoformat(),
                "saved_utc": NOW.isoformat(),
                "player_id": player_id,
                "player_name": player.get(
                    "player_name", ""
                ),
                "team": team,
                "opponent": opponent,
                "projected_minutes": round(
                    projected_minutes, 2
                ),
                "position": position,
                "baseline_games": games_played,
            }

            teammate_boost = team_boosts.get(
                team, 0.0
            )

            for stat in STATS:
                baseline = number(
                    player.get(stat + "_pg")
                )

                season_rate = (
                    baseline / season_minutes
                )

                valid_recent = [
                    log
                    for log in recent
                    if (
                        str(log.get(stat, "")).strip()
                        and minutes(log) > 0
                    )
                ]

                total_recent_minutes = sum(
                    minutes(log)
                    for log in valid_recent
                )

                recent_rate = (
                    sum(
                        number(log.get(stat))
                        for log in valid_recent
                    ) / total_recent_minutes
                    if total_recent_minutes > 0
                    else season_rate
                )

                if stat == "points":

                    # Points formula:
                    # 55% season scoring rate
                    # 30% last 10 scoring rate
                    # 15% last 5 scoring rate

                    def scoring_rate(sample):
                        usable = [
                            log
                            for log in sample
                            if (
                                minutes(log) > 0
                                and str(
                                    log.get("points", "")
                                ).strip()
                            )
                        ]

                        total_minutes = sum(
                            minutes(log)
                            for log in usable
                        )

                        if total_minutes <= 0:
                            return season_rate

                        return (
                            sum(
                                number(log.get("points"))
                                for log in usable
                            ) / total_minutes
                        )

                    rate = (
                        0.55 * season_rate
                        + 0.30 * scoring_rate(
                            recent[:10]
                        )
                        + 0.15 * scoring_rate(
                            recent[:5]
                        )
                    )

                else:

                    # Existing formulas for REB,
                    # AST, 3PM, STL and BLK.

                    season_weight = (
                        games_played /
                        (games_played + 12)
                    )

                    stabilized = (
                        season_weight * season_rate
                        + (1 - season_weight)
                        * recent_rate
                    )

                    recent_weight = (
                        len(valid_recent) /
                        (len(valid_recent) + 10)
                    )

                    rate = (
                        (1 - recent_weight) * stabilized
                        + recent_weight * recent_rate
                    )

                defense_factor = 1.0

                if opponent_defense:
                    defense_key = (
                        opponent_defense.get(
                            "position_type", ""
                        ),
                        opponent_defense.get(
                            "position", ""
                        ),
                        stat,
                    )

                    total, appearances = averages[
                        defense_key
                    ]

                    league_average = (
                        total / appearances
                        if appearances > 0
                        else 0.0
                    )

                    if league_average > 0:
                        defense_games = number(
                            opponent_defense.get(
                                "player_games"
                            )
                        )

                        raw_factor = (
                            number(
                                opponent_defense.get(
                                    stat + "_allowed_pg"
                                )
                            ) / league_average
                        )

                        defense_factor = max(
                            0.85,
                            min(
                                1.15,
                                1
                                + (
                                    defense_games /
                                    (defense_games + 20)
                                )
                                * 0.5
                                * (raw_factor - 1),
                            ),
                        )

                # Match the website's injury boost.
                estimate = (
                    projected_minutes
                    * rate
                    * defense_factor
                    * (1 + teammate_boost)
                )

                record["pred_" + stat] = round(
                    max(0.0, estimate),
                    3,
                )

                record["baseline_" + stat] = round(
                    baseline,
                    3,
                )

            history.append(record)

            existing.add(
                (game_key, player_id)
            )

            new_predictions += 1

    write(
        HISTORY,
        HISTORY_FIELDS,
        history,
    )

    # Compare predictions with actual results.

    results = []

    for record in history:
        tipoff = when(
            record.get("tipoff_utc")
        )

        if tipoff is None:
            continue

        if NOW < tipoff + dt.timedelta(hours=2):
            continue

        candidates = [
            log
            for log in by_player.get(
                str(record["player_id"]), []
            )
            if (
                day(log.get("date"))
                == record["game_date"]
                and norm(log.get("opponent"))
                == norm(record["opponent"])
                and minutes(log) > 0
            )
        ]

        if len(candidates) != 1:
            continue

        actual = candidates[0]

        result = dict(
            record,
            actual_minutes=round(
                minutes(actual), 2
            ),
        )

        for stat in STATS:
            if not str(
                actual.get(stat, "")
            ).strip():
                break

            actual_value = number(
                actual.get(stat)
            )

            result["actual_" + stat] = (
                actual_value
            )

            result["error_" + stat] = round(
                abs(
                    number(
                        record.get("pred_" + stat)
                    ) - actual_value
                ),
                3,
            )

        else:
            results.append(result)

    write(
        RESULTS,
        RESULT_FIELDS,
        results,
    )

    print(
        f"Prediction snapshots: {len(history)} total, "
        f"{new_predictions} newly saved; "
        f"scored results: {len(results)}"
    )

    if new_predictions == 0:
        print(
            "No new eligible pregame games "
            "in the next 48 hours."
        )


if __name__ == "__main__":
    run()
