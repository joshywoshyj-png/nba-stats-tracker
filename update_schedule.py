"""
COURTSIDE — NBA SCHEDULE UPDATER
2026-27 NBA Season

Collects NBA games from ESPN.

Includes:
- Yesterday's games (UTC safety buffer)
- Today's games
- Upcoming games

Keeps live games available in Courtside.
"""

import csv
import time

from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


# ============================================================
# SETTINGS
# ============================================================

SEASON = "2026-27"

OUTPUT = Path(__file__).with_name(
    "nba_schedule.csv"
)

FIELDS = [
    "game_id",
    "date_utc",
    "home",
    "away",
    "status",
    "status_detail",
    "season",
    "last_updated_utc"
]

URL = (
    "https://site.api.espn.com/apis/site/v2/"
    "sports/basketball/nba/scoreboard"
)


# ============================================================
# MAIN UPDATER
# ============================================================

def main():

    session = requests.Session()

    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Courtside schedule updater)",
        "Accept": "application/json"
    })

    # IMPORTANT FIX:
    #
    # GitHub Actions uses UTC.
    #
    # In the United States, the UTC date can already
    # be tomorrow while it is still today locally.
    #
    # Start one UTC day earlier so that today's
    # evening games are never skipped.

    today = (
        datetime.now(timezone.utc).date()
        - timedelta(days=1)
    )

    found = {}
    failed = []

    # Collect 16 calendar dates:
    # yesterday in UTC through 14 days ahead.

    for offset in range(0, 16):

        day = today + timedelta(
            days=offset
        )

        print(
            "Checking NBA schedule:",
            day.strftime("%Y%m%d")
        )

        try:

            response = session.get(
                URL,
                params={
                    "dates": day.strftime("%Y%m%d")
                },
                timeout=25
            )

            response.raise_for_status()

            payload = response.json()

            for event in payload.get(
                "events", []
            ):

                competitions = event.get(
                    "competitions", []
                )

                if not competitions:
                    continue

                competition = competitions[0]

                teams = competition.get(
                    "competitors", []
                )

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

                if not home or not away:
                    continue

                status = (
                    competition.get("status")
                    or event.get("status")
                    or {}
                )

                status_type = status.get(
                    "type", {}
                )

                start = (
                    event.get("date")
                    or competition.get("date")
                )

                if not start:
                    continue

                game_id = str(
                    event["id"]
                )

                found[game_id] = {
                    "game_id": game_id,

                    "date_utc": start,

                    "home": home.get(
                        "team", {}
                    ).get(
                        "abbreviation", ""
                    ),

                    "away": away.get(
                        "team", {}
                    ).get(
                        "abbreviation", ""
                    ),

                    "status": status_type.get(
                        "name", ""
                    ),

                    "status_detail": (
                        status_type.get(
                            "shortDetail", ""
                        )
                        or status.get(
                            "displayClock", ""
                        )
                    ),

                    "season": SEASON,

                    "last_updated_utc": (
                        datetime.now(
                            timezone.utc
                        ).isoformat()
                    )
                }

        except (
            requests.RequestException,
            ValueError,
            KeyError
        ) as error:

            failed.append(
                f"{day}: {error}"
            )

        time.sleep(0.1)

    # ========================================================
    # VALIDATE
    # ========================================================

    if not found:

        raise RuntimeError(
            "No NBA schedule games returned. "
            "Previous CSV preserved. "
            f"Errors: {failed[:3]}"
        )

    if failed:

        raise RuntimeError(
            "Some schedule days failed. "
            "Previous CSV preserved. "
            f"Errors: {failed[:5]}"
        )

    # ========================================================
    # SORT GAMES
    # ========================================================

    rows = sorted(
        found.values(),
        key=lambda game: game["date_utc"]
    )

    # ========================================================
    # SAVE
    # ========================================================

    with OUTPUT.open(
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=FIELDS
        )

        writer.writeheader()

        writer.writerows(rows)

    print()
    print("=" * 50)
    print("COURTSIDE NBA SCHEDULE UPDATED!")
    print("=" * 50)

    print(
        "Games saved:",
        len(rows)
    )

    print(
        "File:",
        OUTPUT.name
    )

    print(
        "First game:",
        rows[0]["date_utc"]
    )

    print(
        "Last game:",
        rows[-1]["date_utc"]
    )


if __name__ == "__main__":
    main()
