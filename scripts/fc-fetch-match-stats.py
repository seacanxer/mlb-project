import argparse
import csv
import os
import sys
import time
import json
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

FC_DIR = os.environ.get('FC_DIR', '/home/ubuntu/mlb-project/betting-machine-fc')
DATA_DIR = os.path.join(FC_DIR, 'data')
FEED_URL = 'https://apigw.fotmob.com/matches?date={day}'
MATCH_URL = 'https://www.fotmob.com/match/{mid}'
DESKTOP_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
STAT_KEYS = ('corners', 'yellow_cards', 'red_cards', 'fouls')
CSV_FIELDS = ['Div', 'Date', 'Time', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG',
              'HC', 'AC', 'HY', 'AY', 'HR', 'AR', 'HF', 'AF', 'Referee']
_FRESH = []


def ascii_name(value):
    """FotMob ships accented labels (Cádiz, Leganés); the football-data archive
    and the goal model use ASCII (Cadiz, Leganes). Normalize so the two sources
    key the same team."""
    return ''.join(ch for ch in unicodedata.normalize('NFKD', value or '')
                   if not unicodedata.combining(ch)).strip()


def _fetch(url, timeout=45):
    req = urllib.request.Request(url, headers={'User-Agent': DESKTOP_UA,
                                               'Accept-Encoding': 'identity'})
    return urllib.request.urlopen(req, timeout=timeout).read()


def finished_matches(day):
    root = ET.fromstring(_fetch(FEED_URL.format(day=day)))
    out = []
    for league in root.iter('league'):
        for match in league.iter('match'):
            attr = match.attrib
            if attr.get('Status') != 'F':
                continue
            out.append({
                'match_id': attr.get('id'),
                'league': league.get('name'),
                'home': ascii_name(attr.get('hTeam')),
                'away': ascii_name(attr.get('aTeam')),
                'home_goals': attr.get('hScore'),
                'away_goals': attr.get('aScore'),
                'kickoff_local': attr.get('time'),
            })
    return out


def match_stats(match_id):
    html = _fetch(MATCH_URL.format(mid=match_id)).decode('utf-8', 'replace')
    marker = '__NEXT_DATA__" type="application/json">'
    index = html.find(marker)
    if index < 0:
        return None
    end = html.find('</script>', index)
    if end < 0:
        return None
    try:
        payload = json.loads(html[index + len(marker):end])
    except ValueError:
        return None
    content = (payload.get('props') or {}).get('pageProps', {}).get('content') or {}
    stats = (content.get('stats') or {}).get('Periods', {}).get('All', {}).get('stats') or []
    out = {}
    for section in stats:
        for item in section.get('stats') or []:
            key, values = item.get('key'), item.get('stats')
            if key in STAT_KEYS and isinstance(values, list) and len(values) == 2:
                out[key] = values
    out['referee'] = (((content.get('matchFacts') or {}).get('infoBox') or {})
                      .get('Referee') or {}).get('text') or ''
    return out if 'corners' in out else None


def _matches_for(day, feed_names):
    try:
        matches = finished_matches(day)
    except Exception:
        return []
    keep = []
    for match in matches:
        league = (match['league'] or '').lower()
        if any(name.lower().rstrip('*') in league for name in feed_names):
            keep.append(match)
    return keep


def run(code, feed_names, days, end, workers):
    path = os.path.join(DATA_DIR, f'{code}_stat_history.csv')
    rows = []
    seen = set()
    if os.path.exists(path):
        with open(path, newline='', encoding='utf-8-sig') as handle:
            for row in csv.DictReader(handle):
                if not row.get('HomeTeam'):
                    continue
                key = (row['Date'], row['HomeTeam'], row['AwayTeam'])
                if key in seen:
                    continue
                seen.add(key)
                rows.append({k: ('' if row.get(k) in (None, 'None') else row.get(k))
                             for k in CSV_FIELDS})
    day_keys = [(end - timedelta(days=offset)).strftime('%Y%m%d')
                for offset in range(days)][::-1]

    jobs = []
    for day in day_keys:
        for match in _matches_for(day, feed_names):
            key = (day, match['home'], match['away'])
            if key in seen:
                continue
            jobs.append((day, match))

    added, failed = 0, 0
    if jobs:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(match_stats, j[1]['match_id']): j for j in jobs}
            for future in as_completed(futures):
                day, match = futures[future]
                try:
                    stats = future.result()
                except Exception:
                    stats = None
                if not stats:
                    failed += 1
                    continue
                corners = stats.get('corners') or [None, None]
                yellows = stats.get('yellow_cards') or [None, None]
                reds = stats.get('red_cards') or [None, None]
                fouls = stats.get('fouls') or [None, None]
                rows.append({
                    'Div': code,
                    'Date': datetime.strptime(day, '%Y%m%d').strftime('%d/%m/%Y'),
                    'Time': (match.get('kickoff_local') or '').split(' ')[-1],
                    'HomeTeam': match['home'], 'AwayTeam': match['away'],
                'FTHG': match['home_goals'], 'FTAG': match['away_goals'],
                'HC': corners[0], 'AC': corners[1],
                'HY': yellows[0], 'AY': yellows[1],
                'HR': reds[0], 'AR': reds[1],
                'HF': fouls[0], 'AF': fouls[1],
                'Referee': ascii_name(stats.get('referee', '')),
            })
                added += 1

    rows = sorted({(r['Date'], r['HomeTeam'], r['AwayTeam']): r for r in rows}.values(),
                  key=lambda r: (r['Date'], r['HomeTeam'], r['AwayTeam']))
    tmp = path + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: '' if row.get(k) is None else row[k] for k in CSV_FIELDS})
    os.replace(tmp, path)
    print(json.dumps({'status': 'ok', 'code': code, 'rows': len(rows),
                      'added': added, 'failed': failed, 'path': path}), flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--code', required=True)
    parser.add_argument('--names', required=True)
    parser.add_argument('--days', type=int, default=45)
    parser.add_argument('--end', default=None)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--output')
    args = parser.parse_args(argv)
    end = datetime.strptime(args.end, '%Y%m%d').date() if args.end else \
        datetime.now(timezone.utc).date()
    if args.output:
        global DATA_DIR
        os.makedirs(args.output, exist_ok=True)
        DATA_DIR = os.path.dirname(os.path.abspath(args.output))
    return run(args.code, args.names.split(','), args.days, end, args.workers)


if __name__ == '__main__':
    sys.exit(main())
