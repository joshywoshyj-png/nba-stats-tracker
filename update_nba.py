
# NBA STATS TRACKER — 2026-27 SEASON
# Automatically updates player game logs, season averages,
# and opponent defensive statistics by position.

import time
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
    "minutes", "points", "rebounds", "assists",
    "three_pointers", "steals", "blocks", "turnovers"
]

records = []
failed_games = []


def get_json(url, params=None):
    """Download JSON with retries."""
    for attempt in range(3):
        try:
            response = session.get(
                url, params=params, timeout=25
            )
            response.raise_for_status()
            return response.json()

        except requests.RequestException as error:
            print(f"Request failed: {error}")
            if attempt < 2:
                time.sleep(3 * (attempt + 1))

    return None


def numeric(value, default=0.0):
    """Convert a statistic to a number."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def minutes_number(value):
    """Convert 32:30 into 32.5 minutes."""
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
    """Convert 3-7 into 3 made shots."""
    if value is None:
        return 0.0

    return numeric(str(value).split("-")[0])


def player_position(player):
    """Read player position from ESPN."""
    position = player.get("position", {})

    if isinstance(position, dict):
        position = (
            position.get("abbreviation")
            or position.get("displayName")
            or ""
        )

    return str(position).upper().strip()


def position_group(position):
    """Group positions for defensive comparisons."""
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


def get_games_for_day(day):
    """Find completed NBA games for one date."""
    data = get_json(
        f"{BASE_URL}/scoreboard",
        params={"dates": day.strftime("%Y%m%d")}
    )

    if data is None:
        return None

    games = []

    for event in data.get("events", []):
        competitions = event.get("competitions", [])

        if not competitions:
            continue

        competition = competitions[0]
        status = competition.get("status", {})
        status_type = status.get("type", {})

        if not status_type.get("completed", False):
            continue

        teams = competition.get("competitors", [])

        if len(teams) != 2:
            continue

        home = next(
            (t for t in teams
             if t.get("homeAway") == "home"),
            None
        )

        away = next(
            (t for t in teams
             if t.get("homeAway") == "away"),
            None
        )

        if home is None or away is None:
            continue

        games.append({
            "game_id": str(event["id"]),
            "date": day.isoformat(),
            "home": home["team"]["abbreviation"],
            "away": away["team"]["abbreviation"]
        })

    return games


def get_player_stats(game):
    """Download player box scores for a game."""
    data = get_json(
        f"{BASE_URL}/summary",
        params={"event": game["game_id"]}
    )

    if data is None:
        return None

    boxscore = data.get("boxscore", {})
    teams = boxscore.get("players", [])

    if not teams:
        return None

    game_records = []

    for team in teams:
        team_info = team.get("team", {})
        team_name = team_info.get("abbreviation", "")

        if team_name == game["home"]:
            opponent = game["away"]
        elif team_name == game["away"]:
            opponent = game["home"]
        else:
            continue

        for group in team.get("statistics", []):
            labels = group.get("labels", [])

            for athlete in group.get("athletes", []):
                if athlete.get("didNotPlay", False):
                    continue

                stats = athlete.get("stats", [])
                values = dict(zip(labels, stats))

                minutes = minutes_number(
                    values.get("MIN", "0")
                )

                if minutes <= 0:
                    continue

                player = athlete.get("athlete", {})
                position = player_position(player)

                # ESPN generally reports 3PT as made-attempted.
                three_point_value = values.get(
                    "3PT",
                    values.get("3PM", 0)
                )

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

    return game_records if game_records else None


# --------------------------------------------------
# STEP 1 — COLLECT 2026-27 GAME LOGS
# --------------------------------------------------

today = datetime.now(timezone.utc).date()
day = START_DATE

while day <= today:
    print("Checking", day.strftime("%Y%m%d"))

    games = get_games_for_day(day)

    if games is None:
        failed_games.append(
            f"Scoreboard {day.isoformat()}"
        )
        day += timedelta(days=1)
        continue

    for game in games:
        game_records = get_player_stats(game)

        if game_records is None:
            failed_games.append(
                f"Box score {game['game_id']}"
            )
            continue

        records.extend(game_records)

    day += timedelta(days=1)
    time.sleep(0.15)


# --------------------------------------------------
# STEP 2 — VALIDATE DATA
# --------------------------------------------------

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
    subset=["game_id", "player_id"]
)

games_df = games_df.sort_values(
    ["date", "player_name"]
).reset_index(drop=True)

if games_df["player_id"].eq("").any():
    raise RuntimeError(
        "Some players have missing IDs."
    )

print("Player-game records:", len(games_df))


# --------------------------------------------------
# STEP 3 — SEASON AVERAGES
# --------------------------------------------------

group_columns = [
    "player_id", "player_name", "team"
]

totals = {
    stat: (stat, "sum")
    for stat in STAT_COLUMNS
}

totals["games_played"] = (
    "game_id", "nunique"
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
    datetime.now(timezone.utc).isoformat()
)

season_df = season_df.sort_values(
    "points_pg",
    ascending=False
).reset_index(drop=True)


# --------------------------------------------------
# STEP 4 — OPPONENT DEFENSE BY POSITION
# --------------------------------------------------

# Each row is a player's performance against a team.
# Grouping by opponent tells us what that defense allowed.

def defense_summary(position_column):
    summary = games_df.groupby(
        ["opponent", position_column],
        as_index=False
    ).agg(
        player_games=("player_id", "count"),
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

    summary["position_type"] = position_column
    summary["season"] = SEASON

    return summary


# Exact positions: PG, SG, SF, PF, C, etc.
exact_defense = defense_summary("position")

# Broader groups: G, F, C, etc.
group_defense = defense_summary(
    "position_group"
)

defense_df = pd.concat(
    [exact_defense, group_defense],
    ignore_index=True
)

defense_df = defense_df.sort_values(
    ["opponent", "position_type", "position"]
)


# --------------------------------------------------
# STEP 5 — SAVE CSV FILES
# --------------------------------------------------

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

print()
print("NBA UPDATE COMPLETE!")
print("Season:", SEASON)
print("Player games:", len(games_df))
print("Players:", season_df["player_id"].nunique())
print("Defensive groups:", len(defense_df))
print()
print("Saved:")
print("- nba_game_logs.csv")
print("- nba_stats.csv")
print("- nba_opponent_defense.csv")
