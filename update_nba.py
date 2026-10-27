
# ============================================================
# COURTSIDE — NBA STATISTICS & TEAM PACE UPDATER
# 2026-27 NBA SEASON
#
# Generates:
# nba_game_logs.csv
# nba_stats.csv
# nba_opponent_defense.csv
# nba_team_pace.csv
#
# Source: ESPN NBA completed-game box scores
# ============================================================

import time
import math
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests


SEASON = "2026-27"
START_DATE = date(2026, 10, 20)

BASE_URL = (
    "https://site.api.espn.com/apis/site/v2/"
    "sports/basketball/nba"
)

session = requests.Session()

session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
})

STAT_COLUMNS = [
    "minutes",
    "points",
    "rebounds",
    "assists",
    "three_pointers",
    "three_pointers_attempted",
    "steals",
    "blocks",
    "turnovers"
]

records = []
pace_records = []
failed_games = []


# ============================================================
# GENERAL HELPERS
# ============================================================

def get_json(url, params=None):
    """Download ESPN JSON with retries."""

    for attempt in range(3):
        try:
            response = session.get(
                url,
                params=params,
                timeout=25
            )

            response.raise_for_status()

            return response.json()

        except requests.RequestException as error:
            print("Request failed:", error)

            if attempt < 2:
                time.sleep(3 * (attempt + 1))

    return None


def numeric(value, default=0.0):
    """Convert a value into a finite number."""

    try:
        result = float(value)

        if math.isfinite(result):
            return result

    except (ValueError, TypeError):
        pass

    return default


def minutes_number(value):
    """Convert ESPN minutes such as 32:30 to 32.5."""

    try:
        parts = str(value).split(":")

        if len(parts) == 2:
            return (
                float(parts[0])
                + float(parts[1]) / 60
            )

        return float(parts[0])

    except (ValueError, TypeError):
        return 0.0


def made_shots(value):
    """Convert a shooting split such as 3-7 to 3."""

    if value is None:
        return 0.0

    return numeric(
        str(value).split("-")[0]
    )


def attempted_shots(value):
    """Convert a shooting split such as 3-7 to 7."""

    if value is None:
        return None

    parts = str(value).split("-")

    if len(parts) != 2:
        return None

    try:
        result = float(parts[1])

        return (
            result
            if math.isfinite(result)
            else None
        )

    except (ValueError, TypeError):
        return None


def player_position(player):
    """Read a player's position from ESPN."""

    position = player.get("position", {})

    if isinstance(position, dict):
        position = (
            position.get("abbreviation")
            or position.get("displayName")
            or ""
        )

    return str(position).upper().strip()


def position_group(position):
    """Group player positions for defensive comparisons."""

    position = str(position).upper()

    if position in ("PG", "SG", "G"):
        return "G"

    if position in ("SF", "PF", "F"):
        return "F"

    if position == "C":
        return "C"

    if position in ("G-F", "F-G", "GF"):
        return "G-F"

    if position in ("F-C", "C-F", "FC"):
        return "F-C"

    return "Unknown"


# ============================================================
# STEP 1 — FIND COMPLETED NBA GAMES
# ============================================================

def get_games_for_day(day):
    """Find completed NBA games on one date."""

    data = get_json(
        f"{BASE_URL}/scoreboard",
        params={
            "dates": day.strftime("%Y%m%d")
        }
    )

    if data is None:
        return None

    games = []

    for event in data.get("events", []):

        competitions = event.get(
            "competitions", []
        )

        if not competitions:
            continue

        competition = competitions[0]

        status = competition.get(
            "status", {}
        )

        status_type = status.get(
            "type", {}
        )

        if not status_type.get(
            "completed", False
        ):
            continue

        teams = competition.get(
            "competitors", []
        )

        if len(teams) != 2:
            continue

        home = next(
            (
                team for team in teams
                if team.get("homeAway") == "home"
            ),
            None
        )

        away = next(
            (
                team for team in teams
                if team.get("homeAway") == "away"
            ),
            None
        )

        if home is None or away is None:
            continue

        # Four quarters = 48 minutes.
        # Each overtime adds five minutes.

        period = int(
            numeric(status.get("period", 4), 4)
        )

        period = max(4, period)

        game_minutes = (
            48 + max(0, period - 4) * 5
        )

        games.append({
            "game_id": str(event["id"]),
            "date": day.isoformat(),
            "home": home["team"]["abbreviation"],
            "away": away["team"]["abbreviation"],
            "game_minutes": game_minutes
        })

    return games


# ============================================================
# STEP 2 — READ PLAYER BOX SCORES
# ============================================================

def get_game_stats(game):
    """
    Download player box scores and calculate
    estimated team possessions from the same data.
    """

    data = get_json(
        f"{BASE_URL}/summary",
        params={
            "event": game["game_id"]
        }
    )

    if data is None:
        return None

    boxscore = data.get("boxscore", {})

    teams = boxscore.get("players", [])

    if not teams:
        return None

    game_records = []

    # Collect shooting and possession components
    # for each team using player box scores.

    team_totals = {}

    for team in teams:

        team_info = team.get("team", {})

        team_name = team_info.get(
            "abbreviation", ""
        )

        if team_name == game["home"]:
            opponent = game["away"]

        elif team_name == game["away"]:
            opponent = game["home"]

        else:
            continue

        totals = {
            "fga": 0.0,
            "fta": 0.0,
            "oreb": 0.0,
            "turnovers": 0.0,
            "complete": True,
            "players": 0
        }

        for group in team.get(
            "statistics", []
        ):

            labels = group.get(
                "labels", []
            )

            for athlete in group.get(
                "athletes", []
            ):

                if athlete.get(
                    "didNotPlay", False
                ):
                    continue

                stats = athlete.get(
                    "stats", []
                )

                values = dict(
                    zip(labels, stats)
                )

                minutes = minutes_number(
                    values.get("MIN", "0")
                )

                if minutes <= 0:
                    continue

                player = athlete.get(
                    "athlete", {}
                )

                position = player_position(
                    player
                )

                three_point_value = values.get(
                    "3PT",
                    values.get("3PM", 0)
                )

                # Preserve the existing Courtside
                # player game-log format.

                game_records.append({
                    "game_id": game["game_id"],
                    "date": game["date"],
                    "season": SEASON,
                    "player_id": str(
                        player.get("id", "")
                    ),
                    "player_name": player.get(
                        "displayName", ""
                    ),
                    "team": team_name,
                    "opponent": opponent,
                    "position": position,
                    "position_group": position_group(
                        position
                    ),
                    "minutes": minutes,
                    "points": numeric(
                        values.get("PTS", 0)
                    ),
                    "rebounds": numeric(
                        values.get("REB", 0)
                    ),
                    "assists": numeric(
                        values.get("AST", 0)
                    ),
                    "three_pointers": made_shots(
                        three_point_value
                    ),
                    "three_pointers_attempted": attempted_shots(
                        three_point_value
                    ),
                    "steals": numeric(
                        values.get("STL", 0)
                    ),
                    "blocks": numeric(
                        values.get("BLK", 0)
                    ),
                    "turnovers": numeric(
                        values.get("TO", 0)
                    )
                })

                # Extract possession components.

                fg = values.get("FG")
                ft = values.get("FT")

                fga = attempted_shots(fg)
                fta = attempted_shots(ft)

                oreb_raw = values.get(
                    "OREB", None
                )

                turnovers_raw = values.get(
                    "TO", None
                )

                if (
                    fga is None
                    or fta is None
                    or oreb_raw is None
                    or turnovers_raw is None
                ):
                    totals["complete"] = False

                else:
                    totals["fga"] += fga
                    totals["fta"] += fta

                    totals["oreb"] += numeric(
                        oreb_raw
                    )

                    totals["turnovers"] += numeric(
                        turnovers_raw
                    )

                totals["players"] += 1

        team_totals[team_name] = totals

    if not game_records:
        return None

    # ========================================================
    # STEP 3 — ESTIMATE TEAM PACE
    # ========================================================

    # Possessions approximation:
    #
    # FGA + 0.44 * FTA - OREB + TO
    #
    # We calculate possessions for both teams,
    # average them, then normalize to 48 minutes.
    #
    # This is an estimate, not NBA's official pace.
    # Summed player stats can omit team turnovers
    # and team rebounds.

    home_totals = team_totals.get(
        game["home"]
    )

    away_totals = team_totals.get(
        game["away"]
    )

    pace_rows = []

    if (
        home_totals
        and away_totals
        and home_totals["complete"]
        and away_totals["complete"]
        and home_totals["players"] > 0
        and away_totals["players"] > 0
    ):

        def possessions(totals):
            return (
                totals["fga"]
                + 0.44 * totals["fta"]
                - totals["oreb"]
                + totals["turnovers"]
            )

        home_possessions = possessions(
            home_totals
        )

        away_possessions = possessions(
            away_totals
        )

        if (
            home_possessions > 0
            and away_possessions > 0
        ):

            average_possessions = (
                home_possessions
                + away_possessions
            ) / 2

            game_minutes = game[
                "game_minutes"
            ]

            game_pace = (
                average_possessions
                * 48 / game_minutes
            )

            for team_name, opponent, totals in (
                (
                    game["home"],
                    game["away"],
                    home_totals
                ),
                (
                    game["away"],
                    game["home"],
                    away_totals
                )
            ):

                pace_rows.append({
                    "game_id": game["game_id"],
                    "date": game["date"],
                    "team": team_name,
                    "opponent": opponent,
                    "game_minutes": game_minutes,
                    "fga": totals["fga"],
                    "fta": totals["fta"],
                    "oreb": totals["oreb"],
                    "turnovers": totals["turnovers"],
                    "estimated_possessions": round(
                        possessions(totals), 3
                    ),
                    "game_pace": round(
                        game_pace, 3
                    )
                })

    return game_records, pace_rows


# ============================================================
# STEP 4 — COLLECT CURRENT-SEASON GAMES
# ============================================================

today = datetime.now(
    timezone.utc
).date()

day = START_DATE

while day <= today:

    print(
        "Checking",
        day.strftime("%Y%m%d")
    )

    games = get_games_for_day(day)

    if games is None:
        failed_games.append(
            f"Scoreboard {day.isoformat()}"
        )

        day += timedelta(days=1)
        continue

    for game in games:

        result = get_game_stats(game)

        if result is None:
            failed_games.append(
                f"Box score {game['game_id']}"
            )
            continue

        player_rows, pace_rows = result

        records.extend(player_rows)
        pace_records.extend(pace_rows)

    day += timedelta(days=1)

    time.sleep(0.15)


# ============================================================
# STEP 5 — VALIDATE THE DATA
# ============================================================

if failed_games:

    raise RuntimeError(
        "Some games could not be downloaded. "
        "Existing CSV files will not be overwritten. "
        f"Failures: {failed_games[:10]}"
    )

if not records:

    raise RuntimeError(
        "No player game logs were found. "
        "Existing CSV files were preserved."
    )

games_df = pd.DataFrame(records)

games_df = games_df.drop_duplicates(
    subset=[
        "game_id",
        "player_id"
    ]
)

games_df = games_df.sort_values(
    ["date", "player_name"]
).reset_index(drop=True)

if games_df["player_id"].eq("").any():

    raise RuntimeError(
        "Some players have missing IDs."
    )

print(
    "Player-game records:",
    len(games_df)
)


# ============================================================
# STEP 6 — CALCULATE SEASON AVERAGES
# ============================================================

group_columns = [
    "player_id",
    "player_name",
    "team"
]

totals = {
    stat: (stat, "sum")
    for stat in STAT_COLUMNS
}

totals["games_played"] = (
    "game_id",
    "nunique"
)

season_df = games_df.groupby(
    group_columns,
    as_index=False
).agg(**totals)

for stat in STAT_COLUMNS:

    season_df[f"{stat}_pg"] = (
        season_df[stat]
        / season_df["games_played"]
    )

season_df["season"] = SEASON

season_df["last_updated_utc"] = (
    datetime.now(
        timezone.utc
    ).isoformat()
)

season_df = season_df.sort_values(
    "points_pg",
    ascending=False
).reset_index(drop=True)


# ============================================================
# STEP 7 — OPPONENT DEFENSE BY POSITION
# ============================================================

def defense_summary(position_column):

    summary = games_df.groupby(
        [
            "opponent",
            position_column
        ],
        as_index=False
    ).agg(
        player_games=(
            "player_id",
            "count"
        ),
        **{
            stat: (stat, "sum")
            for stat in STAT_COLUMNS
        }
    )

    for stat in STAT_COLUMNS:

        summary[f"{stat}_allowed_pg"] = (
            summary[stat]
            / summary["player_games"]
        )

    summary = summary.rename(
        columns={
            position_column: "position"
        }
    )

    summary["position_type"] = (
        position_column
    )

    summary["season"] = SEASON

    return summary


exact_defense = defense_summary(
    "position"
)

group_defense = defense_summary(
    "position_group"
)

defense_df = pd.concat(
    [
        exact_defense,
        group_defense
    ],
    ignore_index=True
)

defense_df = defense_df.sort_values(
    [
        "opponent",
        "position_type",
        "position"
    ]
)


# ============================================================
# STEP 8 — CALCULATE TEAM PACE
# ============================================================

PACE_COLUMNS = [
    "team",
    "season",
    "games_played",
    "season_pace",
    "last_10_pace",
    "last_5_pace",
    "league_average_pace",
    "adjusted_pace",
    "last_updated_utc"
]

if pace_records:

    pace_df = pd.DataFrame(
        pace_records
    )

    pace_df = pace_df.drop_duplicates(
        subset=[
            "game_id",
            "team"
        ]
    )

    pace_df = pace_df.sort_values(
        [
            "team",
            "date"
        ]
    )

    # Each team has one row per game.
    # We use total possessions and total
    # game minutes for season pace.

    pace_results = []

    league_pace = (
        pace_df["estimated_possessions"].sum()
        / pace_df["game_minutes"].sum()
        * 48
    )

    for team_name, team_games in pace_df.groupby(
        "team"
    ):

        team_games = team_games.sort_values(
            "date"
        )

        game_count = len(
            team_games
        )

        def pace_for(sample):

            if sample.empty:
                return league_pace

            return (
                sample[
                    "estimated_possessions"
                ].sum()
                / sample[
                    "game_minutes"
                ].sum()
                * 48
            )

        season_pace = pace_for(
            team_games
        )

        last_10_pace = pace_for(
            team_games.tail(10)
        )

        last_5_pace = pace_for(
            team_games.tail(5)
        )

        # Early-season stabilization:
        #
        # Blend team pace with the league average.
        # As more games are played, the team's
        # own pace gets more weight.
        #
        # The 10-game prior is a starting
        # assumption, not a fitted parameter.

        team_weight = (
            game_count
            / (game_count + 10)
        )

        adjusted_pace = (
            team_weight * season_pace
            + (1 - team_weight)
            * league_pace
        )

        pace_results.append({
            "team": team_name,
            "season": SEASON,
            "games_played": game_count,
            "season_pace": round(
                season_pace, 3
            ),
            "last_10_pace": round(
                last_10_pace, 3
            ),
            "last_5_pace": round(
                last_5_pace, 3
            ),
            "league_average_pace": round(
                league_pace, 3
            ),
            "adjusted_pace": round(
                adjusted_pace, 3
            ),
            "last_updated_utc": datetime.now(
                timezone.utc
            ).isoformat()
        })

    team_pace_df = pd.DataFrame(
        pace_results,
        columns=PACE_COLUMNS
    )

    team_pace_df = team_pace_df.sort_values(
        "team"
    )

else:

    print(
        "WARNING: No valid pace records found."
    )

    # Preserve existing pace data if ESPN
    # didn't provide the required box-score
    # shooting statistics.

    try:
        team_pace_df = pd.read_csv(
            "nba_team_pace.csv"
        )

    except FileNotFoundError:
        team_pace_df = pd.DataFrame(
            columns=PACE_COLUMNS
        )


# ============================================================
# STEP 9 — SAVE ALL CSV FILES
# ============================================================

games_df.to_csv(
    "nba_game_logs.csv",
    index=False
)

season_df.to_csv(
    "nba_stats.csv",
    index=False
)

defense_df.to_csv(
    "nba_opponent_defense.csv",
    index=False
)

team_pace_df.to_csv(
    "nba_team_pace.csv",
    index=False
)


# ============================================================
# STEP 10 — FINISHED
# ============================================================

print()
print("=" * 50)
print("COURTSIDE NBA UPDATE COMPLETE!")
print("=" * 50)

print("Season:", SEASON)

print(
    "Player games:",
    len(games_df)
)

print(
    "Players:",
    season_df[
        "player_id"
    ].nunique()
)

print(
    "Defensive groups:",
    len(defense_df)
)

print(
    "Teams with pace data:",
    len(team_pace_df)
)

print()
print("Saved:")
print("- nba_game_logs.csv")
print("- nba_stats.csv")
print("- nba_opponent_defense.csv")
print("- nba_team_pace.csv")

print()
print(
    "NOTE: Pace values are estimated from "
    "ESPN box scores, not official NBA pace."
)
