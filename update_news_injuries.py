
"""Fetch ESPN NBA news and injury reports for Courtside. Run from repository root."""
import csv
import datetime as dt
import json
import re
import time
import urllib.request

ROOT = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/'
NOW = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; CourtsideStats/1.0)', 'Accept': 'application/json'}

def get(path):
    req = urllib.request.Request(ROOT + path, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.load(res)

def write(path, columns, records):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows([{k: record.get(k, '') for k in columns} for record in records])

def string(x):
    return x if isinstance(x, str) else ''

def link(article):
    links = article.get('links') or {}
    return ((links.get('web') or {}).get('href') or ((links.get('web') or {}).get('self') or {}).get('href') or '')

def news():
    data = get('news?limit=35')
    items = data.get('articles') or data.get('headlines') or []
    records = []
    for item in items:
        title = item.get('headline') or item.get('title')
        if not title:
            continue
        records.append(dict(headline=title, url=link(item), published_utc=item.get('published') or item.get('lastModified') or '', summary=item.get('description') or '', last_updated_utc=NOW))
    if not records:
        raise ValueError('ESPN news returned no headlines; retaining previous CSV')
    write('nba_news.csv', ['headline', 'url', 'published_utc', 'summary', 'last_updated_utc'], records)
    print('Saved', len(records), 'news items')

def team_lookup():
    """Build ESPN team ID/name -> abbreviation lookup."""
    lookup = {}
    data = get('teams?limit=100')
    for sport in data.get('sports') or []:
        for league in sport.get('leagues') or []:
            for wrapper in league.get('teams') or []:
                team = wrapper.get('team') or wrapper
                if not isinstance(team, dict):
                    continue
                abbr = team.get('abbreviation') or ''
                if not abbr:
                    continue
                for key in ('id', 'uid', 'displayName', 'name', 'shortDisplayName',
                            'location', 'abbreviation', 'slug'):
                    value = team.get(key)
                    if value:
                        lookup[str(value).strip().lower()] = abbr
    return lookup

def extract_team(group, lookup):
    """ESPN sometimes supplies only team.id, not team.abbreviation."""
    team = group.get('team') or {}
    candidates = []
    if isinstance(team, dict):
        candidates.extend(team.get(k) for k in
                          ('abbreviation', 'id', 'uid', 'displayName', 'name',
                           'shortDisplayName', 'location', 'slug'))
    elif team:
        candidates.append(team)
    candidates.extend(group.get(k) for k in
                      ('teamId', 'team_id', 'teamAbbreviation'))
    for candidate in candidates:
        if candidate is None:
            continue
        key = str(candidate).strip().lower()
        if key in lookup:
            return lookup[key]
        # An already-supplied abbreviation is safe to preserve.
        if re.fullmatch(r'[A-Za-z]{2,4}', str(candidate).strip()):
            return str(candidate).strip().upper()
    return ''

def injuries():
    data = get('injuries')
    groups = data.get('injuries')
    if groups is None:
        raise ValueError('ESPN injury response missing injuries array; retaining previous CSV')
    try:
        lookup = team_lookup()
    except Exception as exc:
        print(f'WARNING: team lookup unavailable: {exc}')
