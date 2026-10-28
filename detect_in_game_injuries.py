
import csv
import html
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

RESULTS_FILE = Path("nba_prediction_results.csv")
INJURIES_FILE = Path("nba_in_game_injuries.csv")

ESPN_SCOREBOARD = (
    "https://site.api.espn.com/apis/site/v2/"
    "sports/basketball/nba/scoreboard"
)
ESPN_SUMMARY = (
    "https://site.api.espn.com/apis/site/v2/"
    "sports/basketball/nba/summary"
)

FIELDS = ["game_key", "player_id", "confirmed", "note"]

# Avoid treating ordinary low minutes as proof of injury.
MIN_EXPECTED_MINUTES = 18
MAX_MINUTES_RATIO = 0.75
MAX_ACTUAL_MINUTES = 25

# Review recent completed games on each run.
LOOKBACK_DAYS = 14

INJURY_TERMS = re.compile(
    r"\b(injur(?:y|ed)|ankle|knee|hamstring|groin|"
    r"shoulder|wrist|back spasms?|concussion|"
    r"calf|foot|hip|quad|thigh|illness)\b",
    re.IGNORECASE,
)

EXIT_TERMS = re.compile(
    r"\b(left the game|left the contest|"
    r"exited the game|exited the contest|"
    r"was ruled out|did not return|"
    r"would not return|won't return|"
    r"will not return|forced to leave|"
    r"left early|departed early)\b",
    re.IGNORECASE,
)


def read_csv(path):
    if not path.exists():
        return []
    with path.open(
        "r", newline="", encoding="utf-8-sig"
    ) as file:
        return list(csv.DictReader(file))


def write_csv(path, rows):
    with path.open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file, fieldnames=FIELDS, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def clean_text(value):
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]*>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_team(value):
    return str(value or "").strip().upper()


def get_json(session, url, params):
    try:
        response = session.get(
            url,
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as error:
        print("ESPN request failed:", error)
        return {}


def get_events(session, day, cache):
    key = day.strftime("%Y%m%d")

    if key not in cache:
        data = get_json(
            session,
            ESPN_SCOREBOARD,
            {"dates": key, "limit": 100},
        )
        cache[key] = data.get("events", [])

    return cache[key]


def matching_event(session, game_day, team, opponent, cache):
    wanted = {normalize_team(team), normalize_team(opponent)}

    # Account for games near midnight and date differences.
    for offset in (-1, 0, 1):
        day = game_day + timedelta(days=offset)

        for event in get_events(session, day, cache):
            competitions = event.get("competitions", [])

            if not competitions:
                continue

            competitors = competitions[0].get(
                "competitors", []
            )

            abbreviations = {
                normalize_team(
                    competitor.get("team", {}).get(
                        "abbreviation"
                    )
                )
                for competitor in competitors
            }

            if abbreviations == wanted:
                status = event.get("status", {})
                status_type = status.get("type", {})

                if status_type.get("completed") is True:
                    return event

    return None


def recap_text(summary):
    pieces = []

    # ESPN may provide recap articles in this section.
    news = summary.get("news", {})

    for article in news.get("articles", []):
        for field in (
            "headline",
            "description",
            "story",
        ):
            value = article.get(field)

            if value:
                pieces.append(clean_text(value))

    # Include any text-based game notes when available.
    for item in summary.get("plays", []):
        if isinstance(item, dict):
            value = item.get("text")

            if value:
                pieces.append(clean_text(value))

    return " ".join(pieces)


def find_injury_evidence(player_name, text):
    if not player_name or not text:
        return None

    escaped_name = re.escape(player_name.strip())

    # Split recap text into sentences.
    sentences = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    for sentence in sentences:
        if not re.search(
            r"\b" + escaped_name + r"\b",
            sentence,
            re.IGNORECASE,
        ):
            continue

        # Both injury evidence and an early departure
        # must appear in the same sentence.
        if not INJURY_TERMS.search(sentence):
            continue

        if not EXIT_TERMS.search(sentence):
            continue

        return sentence[:400]

    return None


def main():
    results = read_csv(RESULTS_FILE)
    existing = read_csv(INJURIES_FILE)

    if not results:
        print("No completed prediction results to check.")
        return

    existing_keys = {
        (
            row.get("game_key", "").strip(),
            row.get("player_id", "").strip(),
        )
        for row in existing
    }

    today = datetime.now(timezone.utc).date()

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Courtside-Stats-Tracker/1.0"
    })

    event_cache = {}
    summary_cache = {}

    checked = 0
    confirmed = 0

    for row in results:
        game_key = str(row.get("game_key", "")).strip()
        player_id = str(row.get("player_id", "")).strip()
        player_name = str(
            row.get("player_name", "")
        ).strip()

        key = (game_key, player_id)

        if not all(key) or key in existing_keys:
            continue

        try:
            game_day = date.fromisoformat(
                str(row.get("game_date", ""))[:10]
            )
        except ValueError:
            continue

        age = (today - game_day).days

        if age < 0 or age > LOOKBACK_DAYS:
            continue

        expected_minutes = number(
            row.get("projected_minutes")
        )
        actual_minutes = number(
            row.get("actual_minutes")
        )

        if expected_minutes < MIN_EXPECTED_MINUTES:
            continue

        if actual_minutes <= 0:
            continue

        if actual_minutes > MAX_ACTUAL_MINUTES:
            continue

        if (
            actual_minutes / expected_minutes
            > MAX_MINUTES_RATIO
        ):
            continue

        team = row.get("team", "")
        opponent = row.get("opponent", "")

        if not team or not opponent or not player_name:
            continue

        checked += 1

        event = matching_event(
            session,
            game_day,
            team,
            opponent,
            event_cache,
        )

        if not event:
            continue

        event_id = str(event.get("id", ""))

        if not event_id:
            continue

        if event_id not in summary_cache:
            summary_cache[event_id] = get_json(
                session,
                ESPN_SUMMARY,
                {"event": event_id},
            )

        summary = summary_cache[event_id]
        text = recap_text(summary)

        evidence = find_injury_evidence(
            player_name,
            text,
        )

        if not evidence:
            continue

        existing.append({
            "game_key": game_key,
            "player_id": player_id,
            "confirmed": "YES",
            "note": (
                "Auto-detected from ESPN game recap "
                f"(event {event_id}): {evidence}"
            ),
        })

        existing_keys.add(key)
        confirmed += 1

        print(
            "Confirmed possible in-game injury:",
            player_name,
            game_day,
        )

    write_csv(INJURIES_FILE, existing)

    print()
    print("COURTSIDE IN-GAME INJURY DETECTION")
    print("Low-minute cases checked:", checked)
    print("New evidence-matched cases:", confirmed)
    print("Total injury CSV entries:", len(existing))


if __name__ == "__main__":
    main()
