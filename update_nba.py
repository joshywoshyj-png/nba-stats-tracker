
import requests

url = (
    "https://site.api.espn.com/apis/site/v2/"
    "sports/basketball/nba/scoreboard"
)

print("Testing ESPN NBA connection...")

try:
    response = requests.get(url, timeout=20)
    response.raise_for_status()

    data = response.json()
    games = data.get("events", [])

    print("SUCCESS! ESPN connection works.")
    print("Games returned:", len(games))

except requests.exceptions.RequestException as error:
    print("ESPN connection failed.")
    raise
