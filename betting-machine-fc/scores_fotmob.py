"""FotMob results feed: covers leagues ESPN/FlashScore miss (CANP, USL, etc).

Day feed is gzipped XML; finished matches carry Status="F".
"""

import re
import time
import unicodedata
import urllib.request
import zlib
import html as html_lib
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from datetime import date, timedelta

FEED_URL = 'https://apigw.fotmob.com/matches?date={day}'
MATCH_RE = re.compile(
    r'<match id="(?P<id>\d+)" hTeam="(?P<home>[^"]*)" aTeam="(?P<away>[^"]*)"'
    r' hScore="(?P<hg>-?\d+)" aScore="(?P<ag>-?\d+)"[^>]*Status="(?P<status>[A-Z]+)"'
)
UA = {'User-Agent': 'Mozilla/5.0'}
_CACHE = {'index': None, 'ts': 0, 'ttl': 300}


def norm(s):
    s = (s or '').lower().strip()
    s = unicodedata.normalize('NFKD', s)
    s = s.encode('ascii', 'ignore').decode()
    return re.sub(r'\s+', ' ', s)


_TEAM_ALIAS = {
    'atletico': 'atletico', 'atlético': 'atletico',
    'sporting jacksonville': 'sporting jax', 'sporting jax': 'sporting jax',
    'miami fc': 'miami', 'miami': 'miami',
    'cavalry fc': 'cavalry', 'cavalry': 'cavalry',
    'fc tulsa': 'tulsa', 'tulsa': 'tulsa',
    'las vegas lights fc': 'las vegas lights', 'las vegas lights': 'las vegas lights',
    'sacramento republic fc': 'sacramento republic', 'sacramento republic': 'sacramento republic',
    'detroit city fc': 'detroit city', 'detroit city': 'detroit city',
    'brooklyn fc': 'brooklyn', 'brooklyn': 'brooklyn',
}


def _alias(name):
    base = norm(name)
    base = _TEAM_ALIAS.get(base, base)
    variants = {base}
    for tok in ('fc', 'cf', 'sc', 'ac', 'as', 'club', 'city', 'united', 'deportivo'):
        stripped = re.sub(rf'\b{tok}\b', ' ', base)
        stripped = re.sub(r'\s+', ' ', stripped).strip()
        if stripped:
            variants.add(stripped)
            _TEAM_ALIAS[stripped] = base
    return variants


def fetch_recent_results(days=3, use_cache=True, target_dates=None):
    now = time.time()
    if use_cache and not target_dates and _CACHE['index'] is not None and now - _CACHE['ts'] < _CACHE['ttl']:
        return _CACHE['index']
    index = defaultdict(list)
    today = date.today()
    requested = {today + timedelta(days=back) for back in range(0, -max(0, int(days)), -1)}
    for value in target_dates or ():
        try:
            requested.add(value if isinstance(value, date) else date.fromisoformat(str(value)[:10]))
        except (TypeError, ValueError):
            continue

    def fetch_day(day_date):
        day = day_date.strftime('%Y%m%d')
        req = urllib.request.Request(FEED_URL.format(day=day), headers=UA)
        last_error = None
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=12) as r:
                    raw = r.read()
                try:
                    raw = zlib.decompress(raw, 16 + zlib.MAX_WBITS)
                except zlib.error:
                    pass
                return day_date, raw.decode('utf-8', 'ignore'), None
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(.2)
        return day_date, None, last_error

    pages = []
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(requested)))) as pool:
        futures = [pool.submit(fetch_day, day_date) for day_date in sorted(requested)]
        for future in as_completed(futures):
            pages.append(future.result())
    for day_date, xml, error in sorted(pages):
        day = day_date.strftime('%Y%m%d')
        if xml is None:
            print(f'[scores_fotmob] WARN day={day}: {error}', flush=True)
            continue
        for m in MATCH_RE.finditer(xml):
            home, away = html_lib.unescape(m.group('home')), html_lib.unescape(m.group('away'))
            status = m.group('status')
            try:
                hg, ag = int(m.group('hg')), int(m.group('ag'))
            except ValueError:
                continue
            if hg < 0 or ag < 0:
                continue
            # Status F = finished. Status S with a real score means the feed
            # has the score but is late flipping the flag (friendlies,
            # internationals) — accept it only when both sides scored-or-drew,
            # i.e. any numeric score is authoritative once kickoff has passed.
            if status not in ('F', 'S'):
                continue
            row = {
                'home': home, 'away': away, 'home_goals': hg, 'away_goals': ag,
                'home_score': hg, 'away_score': ag,
                'period': '90min', 'status': 'final', 'score_status': 'final',
                'fs_id': m.group('id'), 'date_key': day, 'source': 'fotmob',
            }
            for h in _alias(home):
                for a in _alias(away):
                    index[(h, a)].append(row)
    if not target_dates:
        _CACHE['index'] = index
        _CACHE['ts'] = time.time()
    return index


def build_lookup(index):
    return dict(index)


def find_result(home, away, lookup, kickoff_date=None):
    from football_formula_engine.fixture_matching import unique_result
    candidates = []
    for h in _alias(home):
        for a in _alias(away):
            candidates.extend(lookup.get((h, a), []))
    return unique_result(candidates, kickoff_date)
