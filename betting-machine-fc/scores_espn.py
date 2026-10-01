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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    'spain. la liga': 'esp.1',
    'england. premier league': 'eng.1',
    'england. championship': 'eng.2',
    'england. league one': 'eng.3',
    'england. league two': 'eng.4',
    'germany. bundesliga': 'ger.1',
    'germany. 2. bundesliga': 'ger.2',
    'italy. serie a': 'ita.1',
    'italy. serie b': 'ita.2',
    'france. ligue 1': 'fra.1',
    'france. ligue 2': 'fra.2',
    'netherlands. eredivisie': 'ned.1',
    'portugal. primeira liga': 'por.1',
    'brazil. campeonato brasileiro. serie a': 'bra.1',
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
    for attempt in range(2):
        try:
            r = subprocess.run(['curl', '-s', '-m', '12', '--compressed', url],
                               capture_output=True, timeout=15)
            if r.stdout:
                return json.loads(r.stdout.decode('utf-8', 'replace'))
        except Exception:
            pass
        if attempt == 0:
            time.sleep(.2)
    return None


def fetch_recent_results(days=7, use_cache=True, target_dates=None, leagues=None, league_dates=None):
    now = time.time()
    if use_cache and not target_dates and leagues is None and league_dates is None and _CACHE['index'] is not None and now - _CACHE['ts'] < _CACHE['ttl']:
        return _CACHE['index']
    index = []
    today = date.today()
    requested_dates = {today + timedelta(days=d) for d in range(0, -max(0, int(days)), -1)}
    for value in target_dates or ():
        try:
            requested_dates.add(value if isinstance(value, date) else date.fromisoformat(str(value)[:10]))
        except (TypeError, ValueError):
            continue
    if leagues is None:
        requested_slugs = _SLUGS
    else:
        normalized = {norm(league) for league in leagues if league}
        slug_map = {norm(name): slug for name, slug in LEAGUE_SLUGS.items()}
        requested_slugs = sorted({slug_map[name] for name in normalized if name in slug_map})
    slug_map = {norm(name): slug for name, slug in LEAGUE_SLUGS.items()}
    if league_dates is None:
        targets = {(slug, day) for day in requested_dates for slug in requested_slugs}
    else:
        targets = set()
        for day_value, league in league_dates:
            try:
                day_date = day_value if isinstance(day_value, date) else date.fromisoformat(str(day_value)[:10])
            except (TypeError, ValueError):
                continue
            slug = slug_map.get(norm(league or ''))
            if slug:
                targets.add((slug, day_date))
    pages = []
    tasks = [(slug, day.strftime('%Y%m%d'), day) for slug, day in targets]
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(tasks)))) as pool:
        futures = {pool.submit(_fetch_day, slug, day): (slug, day, day_date)
                   for slug, day, day_date in tasks}
        for future in as_completed(futures):
            slug, day, day_date = futures[future]
            try:
                pages.append((slug, day, day_date, future.result()))
            except Exception:
                pages.append((slug, day, day_date, None))
    for slug, day, day_date, data in sorted(pages, key=lambda row: (row[2], row[0])):
        if not data:
            continue
        for ev in data.get('events') or []:
            try:
                comp = (ev.get('competitions') or [{}])[0]
                competitors = comp.get('competitors') or []
                if len(competitors) < 2:
                    continue
                home = next((item for item in competitors
                             if str(item.get('homeAway') or '').lower() == 'home'), None)
                away = next((item for item in competitors
                             if str(item.get('homeAway') or '').lower() == 'away'), None)
                if home is None or away is None:
                    continue
                status = str((ev.get('status') or {}).get('type', {}).get('name') or '').strip().lower()
                if status not in ('status_full_time', 'full_time', 'final'):
                    continue
                league = ((data.get('leagues') or [{}])[0]).get('name') or slug
                index.append({
                    'home': home.get('team', {}).get('displayName', ''),
                    'away': away.get('team', {}).get('displayName', ''),
                    'home_goals': int(home.get('score')),
                    'away_goals': int(away.get('score')),
                    'date_key': day_date.isoformat(),
                    'league': league,
                    'period': '90min',
                    'status': 'final',
                    'espn_id': comp.get('id'),
                })
            except (TypeError, ValueError, KeyError):
                continue
    if not target_dates and leagues is None and league_dates is None:
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
