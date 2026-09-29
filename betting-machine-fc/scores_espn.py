"""ESPN scoreboard results feed (third lane).

Picks up finished matches the FlashScore and alt feeds do not carry
(e.g. Paraguay. Primera Division). Strict name + date matching, same as
scores_flashscore/scores_alt: no fuzzy fallback, no fabricated scores.

fetch_recent_results() -> index list
build_lookup(index)     -> lookup dict keyed by (norm(home), norm(away))
find_result(home, away, lookup, kickoff_date) -> row or None
"""
import json
import re
import subprocess
import time
import unicodedata
from datetime import date, timedelta

SCOREBOARD_URL = ('https://site.api.espn.com/apis/site/v2/sports/soccer/'
                  '{slug}/scoreboard?dates={day}&limit=200')
# ESPN rejects any explicit User-Agent header (403 Access Denied); no -A at all.

_CACHE = {'ts': 0.0, 'index': None, 'ttl': 600}

LEAGUE_SLUGS = {
    'paraguay. primera division': 'par.1',
    'paraguayan primera division': 'par.1',
    'uefa nations league': 'uefa.nations.league',
    'spain. segunda division': 'esp.2',
    'segunda division': 'esp.2',
}

_SLUGS = sorted(set(LEAGUE_SLUGS.values()))


def norm(s):
    s = unicodedata.normalize('NFKD', s or '')
    s = s.encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9 ]', ' ', s.lower()).strip()


def name_keys(name):
    base = norm(name)
    keys = {base}
    for tok in ('fc', 'cf', 'club', 'deportivo', 'sportivo', 'sc', 'ac', 'as'):
        stripped = re.sub(r'\b%s\b' % tok, ' ', base)
        stripped = re.sub(r'\s+', ' ', stripped).strip()
        if stripped:
            keys.add(stripped)
    return {k for k in keys if k}


def _fetch_day(slug, day):
    url = SCOREBOARD_URL.format(slug=slug, day=day)
    try:
        r = subprocess.run(['curl', '-s', '-m', '25', '--compressed', url],
                           capture_output=True, timeout=30)
        if not r.stdout:
            return None
        return json.loads(r.stdout.decode('utf-8', 'replace'))
    except Exception:
        return None


def fetch_recent_results(days=3, use_cache=True):
    now = time.time()
    if use_cache and _CACHE['index'] is not None and now - _CACHE['ts'] < _CACHE['ttl']:
        return _CACHE['index']
    index = []
    today = date.today()
    for d in range(0, -days, -1):
        day = (today + timedelta(days=d)).strftime('%Y%m%d')
        for slug in _SLUGS:
            data = _fetch_day(slug, day)
            if not data:
                continue
            for ev in data.get('events') or []:
                try:
                    comp = (ev.get('competitions') or [{}])[0]
                    competitors = comp.get('competitors') or []
                    if len(competitors) < 2:
                        continue
                    status = str((ev.get('status') or {}).get('type', {}).get('name') or '').strip().lower()
                    if status not in ('status_full_time', 'full_time', 'final'):
                        continue
                    home = competitors[0]
                    away = competitors[1]
                    league = ((data.get('leagues') or [{}])[0]).get('name') or slug
                    index.append({
                        'home': home.get('team', {}).get('displayName', ''),
                        'away': away.get('team', {}).get('displayName', ''),
                        'home_goals': int(home.get('score')),
                        'away_goals': int(away.get('score')),
                        'date_key': (today + timedelta(days=d)).isoformat(),
                        'league': league,
                        'period': '90min',
                        'status': 'final',
                        'espn_id': comp.get('id'),
                    })
                except (TypeError, ValueError, KeyError):
                    continue
            time.sleep(0.2)
        time.sleep(0.3)
    _CACHE['ts'] = time.time()
    _CACHE['index'] = index
    return index


def build_lookup(index):
    lookup = {}
    for row in index or []:
        for h in name_keys(row.get('home', '')):
            for a in name_keys(row.get('away', '')):
                lookup.setdefault((h, a), []).append(row)
    return lookup


def find_result(home, away, lookup, kickoff_date=None):
    import scores_flashscore
    from football_formula_engine.fixture_matching import unique_result
    candidates = [row for h in name_keys(home)
                  for a in name_keys(away)
                  for row in lookup.get((h, a), [])]
    return unique_result(candidates, kickoff_date)
