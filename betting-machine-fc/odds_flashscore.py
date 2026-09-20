import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = 'https://global.ds.lsapp.eu/odds/pq_graphql'
FEED = 'https://global.flashscore.ninja/2/x/feed/'
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36'

def _get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Referer': 'https://www.flashscore.com/'})
    with urllib.request.urlopen(req, timeout=15) as response:
        return response.read().decode('utf-8', 'replace')

def _norm(value):
    value = (value or '').lower()
    value = re.sub(r'[^a-z0-9 ]+', ' ', value)
    return re.sub(r'\s+', ' ', value).strip()

def _feed_rows(body):
    rows = []
    for chunk in body.split('¬'):
        fields = {}
        for item in chunk.split('¬'):
            pair = item.split('÷', 1)
            if len(pair) == 2:
                fields[pair[0]] = pair[1]
        if fields.get('AA') and fields.get('AE') and fields.get('FH'):
            rows.append(fields)
    return rows

def discover_event(home, away, start_ts):
    date = datetime.fromtimestamp(float(start_ts), timezone.utc).strftime('%Y-%m-%d')
    body = _get(FEED + 'f_1_0_8_en_1')
    candidates = []
    for row in _feed_rows(body):
        rh, ra = _norm(row.get('AE')), _norm(row.get('FH'))
        if rh != _norm(home) or ra != _norm(away):
            continue
        try:
            delta = abs(int(row.get('AD', 0)) - int(float(start_ts)))
        except (TypeError, ValueError):
            continue
        candidates.append((delta, row.get('AA'), row))
    if not candidates:
        return None
    delta, event_id, row = min(candidates)
    if delta > 172800:
        return None
    return {'event_id': event_id, 'home': row.get('AE'), 'away': row.get('FH'), 'start_ts': row.get('AD'), 'date': date}

def fetch_odds(event_id):
    params = {'_hash': 'oce', 'eventId': event_id, 'projectId': '5', 'geoIpCode': 'US', 'geoIpSubdivisionCode': 'USCA'}
    url = BASE + '?' + urllib.parse.urlencode(params)
    raw = _get(url)
    data = json.loads(raw)
    return data.get('data', {}).get('findOddsByEventId', {}).get('odds', [])

def crosscheck(home, away, start_ts, primary_odds):
    captured_at = datetime.now(timezone.utc).isoformat()
    result = {'captured_at': captured_at, 'provider': 'flashscore', 'status': 'unavailable', 'match_verified': False, 'bookmakers': {}}
    try:
        match = discover_event(home, away, start_ts)
        if not match:
            result['reason'] = 'event_not_exactly_matched'
            return result
        result['match'] = match
        result['match_verified'] = True
        odds = fetch_odds(match['event_id'])
        for item in odds:
            bookmaker = item.get('bookmaker') or item.get('bookmakerName') or item.get('name')
            if bookmaker:
                result['bookmakers'].setdefault(bookmaker, []).append(item)
        result['status'] = 'available' if result['bookmakers'] else 'no_bookmaker_odds'
        return result
    except Exception as exc:
        result['reason'] = type(exc).__name__ + ': ' + str(exc)[:180]
        return result
