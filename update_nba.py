
import pandas as pd
from nba_api.stats.endpoints import leaguedashplayerstats
from datetime import datetime, timezone

print("Fetching 2026-27 NBA player statistics...")

stats = leaguedashplayerstats.LeagueDashPlayerStats(
    season="2026-27",
    season_type_all_star="Regular Season",
    timeout=30
)

df = stats.get_data_frames()[0]

# Convert NBA column names to your tracker format
df = df.rename(columns={
    "PLAYER_NAME": "player_name",
    "TEAM_ABBREVIATION": "team",
    "GP": "games_played",
    "PTS": "points",
    "REB": "rebounds",
    "AST": "assists"
})

for stat in ["points", "rebounds", "assists"]:
    df[stat + "_pg"] = (
        df[stat] / df["games_played"].replace(0, float("nan"))
    )

df["season"] = "2026-27"
df["last_updated_utc"] = datetime.now(timezone.utc).isoformat()

df.to_csv("nba_stats.csv", index=False)

print("Updated", len(df), "players!")
