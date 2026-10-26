"""Courtside: publish upcoming NBA games from ESPN's scoreboard feed."""
import csv
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

OUTPUT = Path(__file__).with_name('nba_schedule.csv')
FIELDS = ['game_id','date_utc','home','away','status','status_detail','season','last_updated_utc']
URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard'

def main():
    session = requests.Session()
    session.headers.update({'User-Agent':'Mozilla/5.0 (Courtside schedule updater)', 'Accept':'application/json'})
    today = datetime.now(timezone.utc).date()
    found = {}
    failed = []
    for offset in range(0, 15):
        day = today + timedelta(days=offset)
        try:
            response = session.get(URL, params={'dates':day.strftime('%Y%m%d')}, timeout=25)
            response.raise_for_status()
            payload = response.json()
            for event in payload.get('events', []):
                competition = (event.get('competitions') or [{}])[0]
                teams = competition.get('competitors') or []
                home = next((x for x in teams if x.get('homeAway') == 'home'), None)
                away = next((x for x in teams if x.get('homeAway') == 'away'), None)
                if not home or not away: continue
                status = (competition.get('status') or event.get('status') or {})
                kind = status.get('type') or {}
                start = event.get('date') or competition.get('date')
                if not start: continue
                found[str(event['id'])] = {
                    'game_id':str(event['id']),
                    'date_utc':start,
                    'home':home.get('team',{}).get('abbreviation',''),
                    'away':away.get('team',{}).get('abbreviation',''),
                    'status':kind.get('name',''),
                    'status_detail':kind.get('shortDetail','') or status.get('displayClock',''),
                    'season':'2026-27',
                    'last_updated_utc':datetime.now(timezone.utc).isoformat(),
                }
        except (requests.RequestException, ValueError, KeyError) as exc:
            failed.append(f'{day}: {exc}')
        time.sleep(0.1)
    if not found:
        raise RuntimeError('No schedule games returned; preserving previous CSV. Errors: '+str(failed[:3]))
    # Prevent silently publishing an incomplete schedule after transient failures.
    if failed:
        raise RuntimeError('Some schedule days failed; preserving previous CSV: '+str(failed[:5]))
    rows = sorted(found.values(), key=lambda x:x['date_utc'])
    with OUTPUT.open('w', newline='', encoding='utf-8') as file:
        writer=csv.DictWriter(file,fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(rows)
    print(f'Saved {len(rows)} NBA games to {OUTPUT.name}')

if __name__ == '__main__': main()
