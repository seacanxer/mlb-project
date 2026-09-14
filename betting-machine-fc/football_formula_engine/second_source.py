"""The Odds API event adapter; explicit fixture mappings, no fuzzy auto-approval."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import time
from urllib.parse import urlencode, quote
from urllib.request import urlopen

from .contracts import require
from .live_quotes import QuoteJournal


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def normalize_event(event, mapping, bookmaker, captured_at):
    require(event['id'] == mapping['event_id'], 'Event ID mismatch')
    require(event['sport_key'] == mapping['sport_key'], 'Competition mismatch')
    require(event['home_team'] == mapping['source_home'] and
            event['away_team'] == mapping['source_away'], 'Team mapping mismatch')
    require(abs(timestamp(event['commence_time']) - mapping['fixture']['start_ts']) <= 60,
            'Kickoff mismatch; mapping requires review')
    books = [b for b in event.get('bookmakers', []) if b['key'] == bookmaker]
    require(len(books) == 1, 'Requested bookmaker unavailable or duplicated')
    book = books[0]
    normalized = []
    for market in book['markets']:
        key = market['key']
        if key not in ('h2h', 'totals', 'spreads', 'btts'):
            continue
        updated = market.get('last_update') or book.get('last_update')
        updated = timestamp(updated) if updated else None
        require(updated is None or updated <= captured_at, 'Future source timestamp')
        mk = {'odds_1x2': {}, 'odds_btts': {}, 'odds_ou': {}, 'odds_ah': {}}
        for outcome in market['outcomes']:
            name, price = outcome['name'], outcome['price']
            if key == 'h2h':
                side = {event['home_team']: 1, 'Draw': 2, event['away_team']: 3}.get(name)
                require(side is not None, 'Unknown 1X2 outcome')
                mk['odds_1x2'][side] = price
            elif key == 'btts':
                require(name in ('Yes', 'No'), 'Unknown BTTS outcome')
                mk['odds_btts'][name.lower()] = price
            elif key == 'totals':
                require(name in ('Over', 'Under'), 'Unknown total outcome')
                mk['odds_ou'].setdefault(outcome['point'], {})['9' if name == 'Over' else '10'] = price
            else:
                require(name in (event['home_team'], event['away_team']), 'Unknown handicap outcome')
                side = 'home' if name == event['home_team'] else 'away'
                mk['odds_ah'].setdefault(side, []).append((outcome['point'], price))
        if key == 'h2h':
            require(set(mk['odds_1x2']) == {1, 2, 3}, 'Incomplete three-way soccer market')
        if key == 'btts':
            require(set(mk['odds_btts']) == {'yes', 'no'}, 'Incomplete BTTS market')
        normalized.append((mk, updated))
    require(normalized, 'No supported markets returned')
    return normalized


def collect(mapping, journal, api_key, bookmaker):
    require(bookmaker.lower() not in ('1xbit', '1xbet'), 'Second reference must use a distinct bookmaker')
    query = urlencode({'apiKey': api_key, 'bookmakers': bookmaker,
                       'markets': 'h2h,totals,spreads,btts', 'oddsFormat': 'decimal'})
    url = ('https://api.the-odds-api.com/v4/sports/' + quote(mapping['sport_key'], safe='') +
           '/events/' + quote(mapping['event_id'], safe='') + '/odds?' + query)
    # Exceptions are reported by type only: request URLs contain credentials.
    with urlopen(url, timeout=25) as response:
        event = json.load(response)
    captured = time.time()
    results = []
    for markets, updated in normalize_event(event, mapping, bookmaker, captured):
        observation = journal.record(mapping['fixture'], markets, event, captured_at=captured,
                                     provider='the-odds-api', bookmaker=bookmaker,
                                     source_updated_at=updated)
        results.append(observation['artifact_id'])
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mapping', type=Path, required=True)
    parser.add_argument('--db', type=Path, default=Path(__file__).resolve().parent.parent / 'live_quotes.db')
    args = parser.parse_args(argv)
    key, book = os.environ.get('FC_SECOND_ODDS_API_KEY'), os.environ.get('FC_SECOND_BOOKMAKER')
    if not key or not book:
        print(json.dumps({'status': 'NOT_CONFIGURED', 'official_enabled': False}))
        return 2
    journal = QuoteJournal(args.db)
    mappings = json.loads(args.mapping.read_text())
    results = []
    for mapping in mappings:
        try:
            ids = collect(mapping, journal, key, book)
            results.append({'fixture_id': mapping['fixture']['match_id'], 'status': 'captured', 'ids': ids})
        except Exception as exc:
            results.append({'fixture_id': mapping['fixture']['match_id'], 'status': 'failed',
                            'error_type': type(exc).__name__})
    print(json.dumps({'results': results, 'official_enabled': False}))
    return 1 if any(r['status'] == 'failed' for r in results) else 0


if __name__ == '__main__':
    raise SystemExit(main())
