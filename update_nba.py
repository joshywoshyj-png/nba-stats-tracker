
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
SEASON_START = datetime(2026, 10, 20, tzinfo=timezone.utc)
TODAY = datetime.now(timezone.utc)

session = requests.Session()
records = []

day = SEASON_START

while day <= TODAY:
    date = day.strftime("%Y%m%d")
    print("Checking", date, flush=True)

    scoreboard = session.get(
        f"{BASE}/scoreboard",
        params={"dates": date, "limit": 100},
        timeout=20
    )
    scoreboard.raise_for_status()

    games = scoreboard.json().get("events", [])

    for game in games:
        if not game.get("status", {}).get("type", {}).get("completed"):
            continue

        game_id = game["id"]

        response = session.get(
            f"{BASE}/summary",
            params={"event": game_id},
            timeout=20
        )
        response.raise_for_status()

        data = response.json()

        for team in data.get("boxscore", {}).get("players", []):
            team_name = team.get("team", {}).get("abbreviation", "")

            for group in team.get("statistics", []):
                labels = group.get("labels", [])

                for athlete in group.get("athletes", []):
                    
                    # Skip players who did not play
                    if athlete.get("didNotPlay", False):
                        continue

                    # Skip players with zero minutes
                    stats = athlete.get("stats", [])
                    minutes = stats[0] if stats else "0"

                    try:
                        played_minutes = float(str(minutes).split(":")[0])
                    except (ValueError, TypeError):
                        played_minutes = 0

                    if played_minutes <= 0:
                        continue

                    values = dict(zip(labels, athlete.get("stats", [])))
                    player = athlete.get("athlete", {})

                    def number(key):
                        try:
                            return float(values.get(key, 0))
                        except (ValueError, TypeError):
                            return 0.0

                    records.append({
                        "game_id": game_id,
                        "date": date,
                        "player_id": player.get("id"),
                        "player_name": player.get("displayName"),
                        "team": team_name,
                        "points": number("PTS"),
                        "rebounds": number("REB"),
                        "assists": number("AST"),
                    })

    day += timedelta(days=1)

if not records:
    raise RuntimeError("No player statistics were found.")

games_df = pd.DataFrame(records)
games_df = games_df.drop_duplicates(
    subset=["game_id", "player_id"]
)

games_df.to_csv("nba_game_logs.csv", index=False)

df = games_df.groupby(
    ["player_id", "player_name", "team"],
    as_index=False
).agg(
    games_played=("game_id", "nunique"),
    points=("points", "sum"),
    rebounds=("rebounds", "sum"),
    assists=("assists", "sum")
)

for stat in ["points", "rebounds", "assists"]:
    df[stat + "_pg"] = (
        df[stat] / df["games_played"]
    )

df["season"] = "2026-27"
df["last_updated_utc"] = datetime.now(
    timezone.utc
).isoformat()

df.to_csv("nba_stats.csv", index=False)

print("Updated", len(df), "players!")
print("Collected", len(games_df), "player-game records!")
