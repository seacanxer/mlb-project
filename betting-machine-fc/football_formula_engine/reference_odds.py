"""Bulk sharp-reference capture from The Odds API (one request per league).

Each provider event is attached to a scanned 1xbit fixture only when both
teams resolve to the same league training-team names and kickoffs agree
within ``KICKOFF_TOLERANCE_SECONDS``. Anything ambiguous stays unmatched: a
missing reference only withholds value picks, while a wrong match would
invent edge. Quotes are recorded in the immutable QuoteJournal under the
1xbit fixture ID, so the scanner reads them with the same as-of rules.
"""
import json
import time
from urllib.parse import quote, urlencode
from urllib.request import urlopen

from .second_source import normalize_event, timestamp

API_BASE = 'https://api.the-odds-api.com/v4/sports/'
KICKOFF_TOLERANCE_SECONDS = 60
MARKETS = 'h2h,totals,spreads'

# The Odds API sport keys for supported league codes.
SPORT_KEYS = {
    'E0': 'soccer_epl', 'E1': 'soccer_efl_champ', 'E2': 'soccer_england_league1',
    'E3': 'soccer_england_league2', 'SP1': 'soccer_spain_la_liga',
    'SP2': 'soccer_spain_segunda_division', 'D1': 'soccer_germany_bundesliga',
    'D2': 'soccer_germany_bundesliga2', 'D3': 'soccer_germany_liga3',
    'I1': 'soccer_italy_serie_a', 'I2': 'soccer_italy_serie_b',
    'F1': 'soccer_france_ligue_one', 'F2': 'soccer_france_ligue_two',
    'N1': 'soccer_netherlands_eredivisie', 'P1': 'soccer_portugal_primeira_liga',
    'B1': 'soccer_belgium_first_div', 'T1': 'soccer_turkey_super_league',
    'G1': 'soccer_greece_super_league', 'SC0': 'soccer_spl',
    'IRL0': 'soccer_league_of_ireland', 'BRASB': 'soccer_brazil_serie_b',
    'MEX1': 'soccer_mexico_ligamx',
}


def fetch_league(sport_key, api_key, bookmaker, regions='eu', opener=urlopen):
    query = urlencode({'apiKey': api_key, 'regions': regions, 'bookmakers': bookmaker,
                       'markets': MARKETS, 'oddsFormat': 'decimal'})
    url = API_BASE + quote(sport_key, safe='') + '/odds?' + query
    # Never surface the URL: it contains the credential.
    with opener(url, timeout=25) as response:
        return json.load(response)


def match_events(events, fixtures, resolve):
    """Pair provider events with fixtures. ``resolve(name)`` maps a team name to a
    canonical training name or None. Returns [(fixture_info, event)]."""
    by_key = {}
    for info in fixtures:
        home, away = resolve(info.get('home') or ''), resolve(info.get('away') or '')
        if home and away and home != away:
            by_key.setdefault((home, away), []).append(info)
    pairs, used = [], set()
    for event in events:
        home, away = resolve(event.get('home_team') or ''), resolve(event.get('away_team') or '')
        if not home or not away or home == away:
            continue
        try:
            commence = timestamp(event['commence_time'])
        except (KeyError, TypeError, ValueError):
            continue
        candidates = [info for info in by_key.get((home, away), [])
                      if abs(float(info['start_ts']) - commence) <= KICKOFF_TOLERANCE_SECONDS]
        if len(candidates) != 1 or str(candidates[0]['match_id']) in used:
            continue
        used.add(str(candidates[0]['match_id']))
        pairs.append((candidates[0], event))
    return pairs


def record_event(info, event, journal, bookmaker, captured_at):
    mapping = {'event_id': event['id'], 'sport_key': event['sport_key'],
               'source_home': event['home_team'], 'source_away': event['away_team'],
               'fixture': {'start_ts': float(info['start_ts'])}}
    ids = []
    for markets, updated in normalize_event(event, mapping, bookmaker, captured_at):
        observation = journal.record(info, markets, {'event_id': event['id'], 'sport_key': event['sport_key']},
                                     captured_at=captured_at, provider='the-odds-api',
                                     bookmaker=bookmaker, source_updated_at=updated)
        ids.append(observation['artifact_id'])
    return ids


def capture(fixtures_by_code, resolvers, journal, *, api_key, bookmaker, regions='eu',
            opener=urlopen, now=None):
    """Fetch and record reference quotes. Returns per-league diagnostics."""
    report = {}
    for code, fixtures in sorted(fixtures_by_code.items()):
        sport_key = SPORT_KEYS.get(code)
        if not sport_key or not fixtures or code not in resolvers:
            report[code] = {'status': 'NO_REFERENCE_SPORT_KEY' if not sport_key else 'SKIPPED'}
            continue
        try:
            events = fetch_league(sport_key, api_key, bookmaker, regions, opener)
        except Exception as exc:  # report type only: messages may echo the URL
            report[code] = {'status': 'FETCH_FAILED', 'error_type': type(exc).__name__}
            continue
        captured_at = time.time() if now is None else now
        matched, recorded, failed = 0, 0, 0
        for info, event in match_events(events, fixtures, resolvers[code]):
            matched += 1
            try:
                recorded += bool(record_event(info, event, journal, bookmaker, captured_at))
            except Exception:
                failed += 1
        report[code] = {'status': 'CAPTURED', 'events': len(events), 'fixtures': len(fixtures),
                        'matched': matched, 'recorded': recorded, 'failed': failed}
    return report
