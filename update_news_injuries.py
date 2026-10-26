
"""Fetch ESPN NBA news and injury reports for Courtside."""
import csv
import datetime as dt
import json
import re
import urllib.request

ROOT = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/'
NOW = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; CourtsideStats/1.0)',
    'Accept': 'application/json'
}


def get(path):
    request = urllib.request.Request(ROOT + path, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def write(path, columns, records):
    with open(path, 'w', encoding='utf-8', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows([
            {key: record.get(key, '') for key in columns}
            for record in records
        ])


def link(article):
    links = article.get('links') or {}
    web = links.get('web') or {}
    return web.get('href') or (web.get('self') or {}).get('href') or ''


def news():
    data = get('news?limit=35')
    items = data.get('articles') or data.get('headlines') or []
    records = []

    for item in items:
        title = item.get('headline') or item.get('title')
        if not title:
            continue

        records.append({
            'headline': title,
            'url': link(item),
            'published_utc': item.get('published') or item.get('lastModified') or '',
            'summary': item.get('description') or '',
            'last_updated_utc': NOW
        })

    if not records:
        raise ValueError('ESPN returned no news headlines')

    write('nba_news.csv', [
        'headline', 'url', 'published_utc',
        'summary', 'last_updated_utc'
    ], records)

    print('Saved', len(records), 'news items')


def team_lookup():
    """Match ESPN team IDs and names to abbreviations."""
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

                for field in (
                    'id', 'uid', 'displayName', 'name',
                    'shortDisplayName', 'location',
                    'abbreviation', 'slug'
                ):
                    value = team.get(field)
                    if value:
                        lookup[str(value).strip().lower()] = abbr

    return lookup


def extract_team(group, lookup):
    """Resolve a team from its ESPN information."""
    team = group.get('team') or {}
    candidates = []

    if isinstance(team, dict):
        candidates.extend(
            team.get(field) for field in (
                'abbreviation', 'id', 'uid',
                'displayName', 'name',
                'shortDisplayName', 'location', 'slug'
            )
        )
    elif team:
        candidates.append(team)

    candidates.extend(
        group.get(field) for field in (
            'teamId', 'team_id', 'teamAbbreviation'
        )
    )

    for candidate in candidates:
        if candidate is None:
            continue

        key = str(candidate).strip().lower()

        if key in lookup:
            return lookup[key]

        if re.fullmatch(r'[A-Za-z]{2,4}', str(candidate).strip()):
            return str(candidate).strip().upper()

    return ''


def roster_lookup():
    """Match player IDs and names to their NBA teams."""
    result = {}
    data = get('teams?limit=100')
    teams = []

    for sport in data.get('sports') or []:
        for league in sport.get('leagues') or []:
            for wrapper in league.get('teams') or []:
                team = wrapper.get('team') or wrapper

                if (
                    isinstance(team, dict)
                    and team.get('id')
                    and team.get('abbreviation')
                ):
                    teams.append((
                        str(team['id']),
                        team['abbreviation']
                    ))

    for team_id, abbr in teams:
        try:
            roster = get(f'teams/{team_id}/roster')
            athletes = roster.get('athletes') or []

            for entry in athletes:
                members = (
                    entry.get('items')
                    if isinstance(entry, dict)
                    and isinstance(entry.get('items'), list)
                    else [entry]
                )

                for athlete in members:
                    if not isinstance(athlete, dict):
                        continue

                    for field in ('id', 'displayName', 'fullName'):
                        value = athlete.get(field)
                        if value:
                            result[str(value).strip().lower()] = abbr

        except Exception as exc:
            print(f'WARNING: roster lookup failed for {abbr}: {exc}')

    return result


def injuries():
    data = get('injuries')
    groups = data.get('injuries')

    if groups is None:
        raise ValueError('ESPN injury response missing injuries array')

    try:
        lookup = team_lookup()
    except Exception as exc:
        print('WARNING: team lookup failed:', exc)
        lookup = {}

    records = []
    unresolved = []

    for group in groups:
        team = extract_team(group, lookup)

        entries = (
            group.get('injuries')
            if isinstance(group.get('injuries'), list)
            else [group]
        )

        for item in entries:
            athlete = item.get('athlete') or {}

            if not isinstance(athlete, dict):
                athlete = {}

            player = (
                athlete.get('displayName')
                or athlete.get('fullName')
                or item.get('displayName')
                or ''
            )

            if not player:
                continue

            abbr = (
                extract_team(
                    {'team': item.get('team') or {}},
                    lookup
                )
                or team
            )

            details = item.get('details') or {}
            if not isinstance(details, dict):
                details = {}

            status = (
                item.get('status')
                or details.get('status')
                or ''
            )

            if isinstance(status, dict):
                status = (
                    status.get('description')
                    or status.get('name')
                    or status.get('type')
                    or ''
                )

            comment = (
                item.get('shortComment')
                or item.get('longComment')
                or details.get('detail')
                or ''
            )

            if not abbr:
                unresolved.append(len(records))

            records.append({
                'player_id': str(
                    athlete.get('id')
                    or item.get('athleteId')
                    or ''
                ),
                'player_name': player,
                'team': abbr,
                'status': status if isinstance(status, str) else '',
                'injury': (
                    item.get('type')
                    or details.get('type')
                    or ''
                ) if isinstance(
                    item.get('type') or details.get('type') or '',
                    str
                ) else '',
                'detail': comment if isinstance(comment, str) else '',
                'reported_utc': (
                    item.get('date')
                    or item.get('lastUpdated')
                    or ''
                ),
                'last_updated_utc': NOW
            })

    if unresolved:
        try:
            rosters = roster_lookup()

            for index in unresolved:
                record = records[index]

                record['team'] = (
                    rosters.get(record['player_id'].strip().lower())
                    or rosters.get(record['player_name'].strip().lower())
                    or ''
                )

                if not record['team']:
                    print(
                        'WARNING: team unresolved for',
                        record['player_name']
                    )

        except Exception as exc:
            print('WARNING: roster fallback failed:', exc)

    write('nba_injuries.csv', [
        'player_id', 'player_name', 'team',
        'status', 'injury', 'detail',
        'reported_utc', 'last_updated_utc'
    ], records)

    print('Saved', len(records), 'injury records')


if __name__ == '__main__':
    failed = []

    for label, function in [
        ('news', news),
        ('injuries', injuries)
    ]:
        try:
            function()
        except Exception as exc:
            failed.append(label)
            print(f'WARNING: {label} update failed: {exc}')

    if len(failed) == 2:
        raise SystemExit(
            'Both ESPN updates failed. Existing CSVs retained.'
        )
