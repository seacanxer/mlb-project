#!/usr/bin/env python3
"""Live FC scan: fixtures + 1xbit odds -> DC projections -> gated picks.

Pipeline (Phase 7 adapter):
  1. scrape 24h fixtures (merged into matches_detailed.json, like
     scripts/fc-scrape-fixtures.py)
  2. for leagues covered by football-data CSVs, fit/load a daily-cached
     Dixon-Coles artifact (betting-machine-fc/models_cache/{CODE}.json)
  3. fetch live odds per fixture from 1xbit, price 1X2/O-U/AH/BTTS with the
     engine payout math, compute EV against the live price
  4. gate (odds >= 1.5, ev >= EV_GATE, conservative_ev >= 0.01), best pick
     per fixture, tier=watch (model is unvalidated -> never official)
  5. atomic writes: picks.json, matches_detailed.json picks merge,
     config.json scan metadata

Run: betting-machine-fc/venv/bin/python scripts/fc-scan-live.py
"""
import difflib
import json
import os
import sys
import time
import unicodedata
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FC_DIR = os.path.join(BASE_DIR, 'betting-machine-fc')
sys.path.insert(0, FC_DIR)

import scraper_1xbit as sc  # noqa: E402
from football_formula_engine.data import load_football_data_csv, stable_id  # noqa: E402
from football_formula_engine.markets import asian_handicap, btts, match_odds, over_under  # noqa: E402
from football_formula_engine.model import FitConfig, fit_dixon_coles, project_fixture  # noqa: E402
from football_formula_engine.value import expected_value, fair_odds, proportional_no_vig  # noqa: E402

FORMULA_VERSION = 'dc-loglink-time-decay-v1'
UNCERTAINTY_PENALTY = 0.02
EV_GATE = 0.03
ODDS_FLOOR = 1.5
ODDS_CAP = 4.0
WINDOW_HOURS = 24
MODELS_CACHE = os.path.join(FC_DIR, 'models_cache')

# football-data code -> (csvs [(file, season)], timezone, 1xbit league names)
LEAGUES = {
    'E0': ([('E0_2425.csv', '2425'), ('E0_2526.csv', '2526')], 'Europe/London',
           ['England. Premier League']),
    'E1': ([('E1_2526.csv', '2526')], 'Europe/London', ['England. Championship']),
    'E2': ([('E2_2526.csv', '2526')], 'Europe/London', ['England. League One']),
    'E3': ([('E3_2526.csv', '2526')], 'Europe/London', ['England. League Two']),
    'SP1': ([('SP1_2526.csv', '2526')], 'Europe/Madrid', ['Spain. La Liga']),
    'SP2': ([('SP2_2526.csv', '2526')], 'Europe/Madrid', ['Spain. Segunda Division']),
    'D1': ([('D1_2526.csv', '2526')], 'Europe/Berlin', ['Germany. Bundesliga']),
    'D2': ([('D2_2526.csv', '2526')], 'Europe/Berlin', ['Germany. 2. Bundesliga']),
    'I1': ([('I1_2526.csv', '2526')], 'Europe/Rome', ['Italy. Serie A']),
    'I2': ([('I2_2526.csv', '2526')], 'Europe/Rome', ['Italy. Serie B']),
    'F1': ([('F1_2526.csv', '2526')], 'Europe/Paris', ['France. Ligue 1']),
    'F2': ([('F2_2526.csv', '2526')], 'Europe/Paris', ['France. Ligue 2']),
    'N1': ([('N1_2526.csv', '2526')], 'Europe/Amsterdam', ['Netherlands. Eredivisie']),
    'P1': ([('P1_2526.csv', '2526')], 'Europe/Lisbon', ['Portugal. Primeira Liga']),
    'B1': ([('B1_2526.csv', '2526')], 'Europe/Brussels',
           ['Belgium. First Division A', 'Belgium. Division 1']),
    'T1': ([('T1_2526.csv', '2526')], 'Europe/Istanbul',
           ['Turkiye. Super Lig', 'Turkey. Super Lig']),
    'G1': ([('G1_2526.csv', '2526')], 'Europe/Athens', ['Greece. Super League']),
    'SC1': ([('SC1_2526.csv', '2526')], 'Europe/London', ['Scotland. Premiership']),
    'SC2': ([('SC2_2526.csv', '2526')], 'Europe/London', ['Scotland. Championship']),
    'SC3': ([('SC3_2526.csv', '2526')], 'Europe/London', ['Scotland. League One']),
}
LEAGUE_BY_NAME = {}
for code, (_csvs, _tz, names) in LEAGUES.items():
    for name in names:
        LEAGUE_BY_NAME[name.lower()] = code

TEAM_ALIASES = {
    'man utd': 'manchester united', 'manchester utd': 'manchester united',
    'man city': 'manchester city', 'manchester c': 'manchester city',
    'spurs': 'tottenham hotspur', 'tottenham': 'tottenham hotspur',
    'wolves': 'wolverhampton wanderers', 'wolverhampton': 'wolverhampton wanderers',
    'west ham': 'west ham united', 'brighton': 'brighton hove albion',
    'newcastle': 'newcastle united', 'leeds': 'leeds united',
    '1 koln': 'fc koln', 'koln': 'fc koln',
    'borussia monchengladbach': 'm gladbach', 'gladbach': 'm gladbach',
    'paris saint germain': 'paris sg', 'psg': 'paris sg',
    'inter': 'internazionale milano', 'inter milan': 'internazionale milano',
    'milan': 'ac milan', 'roma': 'as roma', 'lazio': 'ss lazio',
    'napoli': 'ssc napoli', 'verona': 'hellas verona',
    'real sociedad': 'sociedad', 'athletic bilbao': 'athletic club',
    'atletico madrid': 'atletico madrid', 'real betis': 'betis',
    'bayer leverkusen': 'leverkusen', 'leipzig': 'rb leipzig',
    'dortmund': 'borussia dortmund', 'bayern': 'bayern munich',
    'n e c': 'nijmegen', 'nec': 'nijmegen',
    'cagliari calcio': 'cagliari', 'angers sco': 'angers',
    'as saint etienne': 'st etienne', 'saint etienne': 'st etienne',
    'usl dunkerque': 'dunkerque', 'ud almeria': 'almeria',
    'fortuna sittard': 'for sittard',
    'vitoria guimaraes': 'v guimaraes',
}
_JUNK_SUFFIXES = (' fc', ' cf', ' sc', ' afc', ' ac', ' us', ' as', ' rc')
CATEGORY_TOKENS = frozenset({
    'ii', 'iii', 'iv', 'u17', 'u18', 'u19', 'u20', 'u21', 'u23',
    'b', 'c', 'res', 'reserves', 'reserve', 'youth', 'women', 'woman',
    'wfc', 'ladies',
})


def norm(s):
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ' '.join(s.lower().replace('.', ' ').replace('-', ' ').split())


def normalize_team_name(name):
    n = norm(name)
    n = TEAM_ALIASES.get(n, n)
    for junk in _JUNK_SUFFIXES:
        if n.endswith(junk):
            n = n[: -len(junk)].strip()
    return TEAM_ALIASES.get(n, n)


def match_team(name, teams):
    if not name or not teams:
        return None
    n = normalize_team_name(name)
    canon = {}
    for t in teams:
        canon.setdefault(normalize_team_name(t), t)
    if n in canon:
        return canon[n]

    def category_locked(a, b):
        toks = set(a.split()) | set(b.split())
        return bool(toks & CATEGORY_TOKENS)

    best, best_r = None, 0.0
    for cn, t in canon.items():
        if category_locked(n, cn):
            continue
        r = difflib.SequenceMatcher(None, n, cn).ratio()
        if r > best_r:
            best, best_r = t, r
    if best_r >= 0.82:
        return best
    toks = set(n.split())
    for cn, t in canon.items():
        if category_locked(n, cn):
            continue
        ctoks = set(cn.split())
        if toks and ctoks and len(toks & ctoks) / len(toks | ctoks) >= 0.5:
            return t
    for cn, t in canon.items():
        if category_locked(n, cn):
            continue
        if len(n) >= 4 and (n in cn or cn in n):
            return t
    return None


def quarter(value):
    q = round(float(value) * 4)
    if abs(float(value) * 4 - q) > 1e-8:
        return None
    return int(q)


def line_str(line):
    return ('%g' % line)


def _sanitize_csv(fpath):
    """Blank non-quarter AH lines in a temp copy (engine contract rejects them).
    Tracked CSV stays untouched; one known bad cell: SP2_2526 row 342."""
    import csv as csvmod
    import tempfile
    with open(fpath, newline='', encoding='utf-8-sig') as f:
        rows = list(csvmod.reader(f))
    if not rows:
        return fpath, False
    header = rows[0]
    cols = [i for i, name in enumerate(header) if name in ('AHh', 'AHCh')]
    changed = False
    for row in rows[1:]:
        for i in cols:
            if i < len(row):
                v = (row[i] or '').strip()
                if not v:
                    continue
                try:
                    fv = float(v)
                except ValueError:
                    row[i] = ''
                    changed = True
                    continue
                q = round(fv * 4)
                if abs(fv * 4 - q) > 1e-8:
                    row[i] = ''
                    changed = True
    if not changed:
        return fpath, False
    tmp = tempfile.NamedTemporaryFile('w', suffix='.csv', newline='', delete=False, encoding='utf-8')
    csvmod.writer(tmp).writerows(rows)
    tmp.close()
    return tmp.name, True


def load_model(code, now):
    """Daily-cached DC fit per league. Returns artifact or None."""
    os.makedirs(MODELS_CACHE, exist_ok=True)
    path = os.path.join(MODELS_CACHE, f'{code}.json')
    today = datetime.fromtimestamp(now, tz=timezone.utc).strftime('%Y-%m-%d')
    if os.path.exists(path):
        try:
            with open(path) as f:
                cached = json.load(f)
            if cached.get('fitted_for_date') == today:
                return cached['artifact']
        except (OSError, ValueError, KeyError):
            pass
    csvs, tz, _names = LEAGUES[code]
    matches = []
    temps = []
    for fname, season in csvs:
        fpath = os.path.join(FC_DIR, 'data', fname)
        if not os.path.exists(fpath):
            continue
        use_path, made_temp = _sanitize_csv(fpath)
        if made_temp:
            temps.append(use_path)
        normalized, _ = load_football_data_csv(use_path, competition_id=code,
                                               season=season, timezone_name=tz)
        matches.extend(normalized)
    for t in temps:
        try:
            os.unlink(t)
        except OSError:
            pass
    if not matches:
        return None
    cutoff = int(now)
    try:
        artifact = fit_dixon_coles(matches, cutoff_utc=cutoff, config=FitConfig())
    except Exception as exc:
        print(f'  [{code}] fit failed: {exc}', file=sys.stderr)
        return None
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump({'fitted_for_date': today, 'artifact': artifact}, f)
    os.replace(tmp, path)
    return artifact


def team_id(code, csv_name):
    return 'fd-team-' + stable_id(code, csv_name)


def csv_teams(code):
    csvs, tz, _ = LEAGUES[code]
    names = set()
    for fname, _season in csvs:
        fpath = os.path.join(FC_DIR, 'data', fname)
        if not os.path.exists(fpath):
            continue
        import csv as csvmod
        with open(fpath, newline='', encoding='utf-8-sig') as f:
            for row in csvmod.DictReader(f):
                for key in ('HomeTeam', 'AwayTeam'):
                    v = (row.get(key) or '').strip()
                    if v:
                        names.add(v)
    return names


def opp(payout, odds, no_vig_probs):
    """One priced opportunity; None when gated out."""
    fo = fair_odds(payout)
    if fo is None:
        return None
    ev = expected_value(payout, odds)
    if not (ODDS_FLOOR <= odds <= ODDS_CAP) or ev < EV_GATE:
        return None
    cev = ev - UNCERTAINTY_PENALTY
    if cev < 0.01:
        return None
    return {'odds': odds, 'fair_odds': fo, 'ev': ev, 'conservative_ev': cev,
            'probability': payout.full_win + 0.5 * payout.half_win,
            'market_probability': no_vig_probs}


def price_fixture(dist, mk):
    """All gated opportunities for one fixture's markets dict."""
    out = []
    one_x_two = mk.get('odds_1x2') or {}
    if all(t in one_x_two for t in (1, 2, 3)):
        try:
            nv = proportional_no_vig([one_x_two[1], one_x_two[2], one_x_two[3]])
        except Exception:
            nv = (None, None, None)
        payouts = match_odds(dist)
        for t, side, label in ((1, 'home', 'Home'), (2, 'draw', 'Draw'), (3, 'away', 'Away')):
            o = opp(payouts[side], float(one_x_two[t]), nv[{1: 0, 2: 1, 3: 2}[t]])
            if o:
                out.append(('1x2', label, o))
    b = mk.get('odds_btts') or {}
    if 'yes' in b and 'no' in b:
        try:
            nv = proportional_no_vig([b['yes'], b['no']])
        except Exception:
            nv = (None, None)
        payouts = btts(dist)
        for side, label, idx in (('yes', 'BTTS Yes', 0), ('no', 'BTTS No', 1)):
            o = opp(payouts[side], float(b[side]), nv[idx])
            if o:
                out.append(('btts', label, o))
    for line, sides in (mk.get('odds_ou') or {}).items():
        try:
            lv = float(line)
        except (TypeError, ValueError):
            continue
        q = quarter(lv)
        if q is None or '9' not in sides or '10' not in sides:
            continue
        try:
            nv = proportional_no_vig([sides['9'], sides['10']])
        except Exception:
            nv = (None, None)
        for side, t, label in (('over', '9', f'Over {line_str(lv)}'),
                               ('under', '10', f'Under {line_str(lv)}')):
            try:
                payout = over_under(dist, side, q)
            except Exception:
                continue
            o = opp(payout, float(sides[t]), nv[0 if side == 'over' else 1])
            if o:
                out.append(('ou', label, o))
    ah = mk.get('odds_ah') or {}
    # 1xbit mirrors lines: home entry p=L pairs with away entry p=-L (same
    # market). Key everything by the HOME-perspective line so both sides of
    # one market land in one bucket; away odds are stored under -p.
    by_line = {}
    for p, c in ah.get('home') or []:
        try:
            by_line.setdefault(float(p), {})['home'] = float(c)
        except (TypeError, ValueError):
            continue
    for p, c in ah.get('away') or []:
        try:
            by_line.setdefault(-float(p), {})['away'] = float(c)
        except (TypeError, ValueError):
            continue
    for p, sides in by_line.items():
        q = quarter(p)
        if q is None or 'home' not in sides or 'away' not in sides:
            continue
        try:
            nv = proportional_no_vig([sides['home'], sides['away']])
        except Exception:
            nv = (None, None)
        for side, idx, label in (('home', 0, f'AH Home {p:+g}'),
                                 ('away', 1, f'AH Away {-p:+g}')):
            try:
                payout = asian_handicap(dist, side, q if side == 'home' else -q)
            except Exception:
                continue
            o = opp(payout, sides[side], nv[idx])
            if o:
                out.append(('ah', label, o))
    return out


def main():
    started = time.time()
    # 1. fixtures
    try:
        rows = sc.list_matches_paginated(window_hours=WINDOW_HOURS, max_pages=60)
    except Exception as exc:
        print(json.dumps({'status': 'error', 'stage': 'fixtures', 'message': str(exc)}))
        return 1
    now = time.time()
    fresh = {}
    for v in rows:
        try:
            mid = str(v.get('I'))
            start = float(v.get('S') or 0)
        except (TypeError, ValueError):
            continue
        if not mid or start <= now:
            continue
        fresh[mid] = {
            'info': {'match_id': mid, 'home': v.get('O1'), 'away': v.get('O2'),
                     'league': v.get('L'), 'start_ts': start,
                     'coverage_status': 'market_only', 'source': '1xbit',
                     'scraped_at': now},
            'picks': [], 'qualified_picks': [],
        }
    merged = dict(fresh)
    matches_path = os.path.join(FC_DIR, 'matches_detailed.json')
    existing = []
    if os.path.exists(matches_path):
        try:
            with open(matches_path) as f:
                existing = json.load(f)
        except (OSError, ValueError):
            existing = []
    for m in existing if isinstance(existing, list) else []:
        info = (m or {}).get('info') or {}
        mid = str(info.get('match_id') or '')
        if not mid:
            continue
        try:
            start = float(info.get('start_ts') or 0)
        except (TypeError, ValueError):
            continue
        if start <= now:
            continue
        if mid in merged:
            for k in ('coverage_status', 'source'):
                if info.get(k):
                    merged[mid]['info'][k] = info[k]
        else:
            merged[mid] = m

    # 2. models for leagues present in the future slate
    models, teams_by_code = {}, {}
    future = [m for m in merged.values() if float(m['info'].get('start_ts') or 0) > now]
    codes_needed = sorted({code for code in
                           (LEAGUE_BY_NAME.get((m['info'].get('league') or '').lower()) for m in future)
                           if code is not None})
    for code in codes_needed:
        print(f'  model {code}...', file=sys.stderr)
        art = load_model(code, now)
        if art:
            models[code] = art
            teams_by_code[code] = csv_teams(code)

    # 3. odds + projection + gate
    picks, scanned, skipped = [], 0, {}
    for m in sorted(future, key=lambda x: float(x['info']['start_ts'])):
        info = m['info']
        code = LEAGUE_BY_NAME.get((info.get('league') or '').lower())
        if not code or code not in models:
            continue
        scanned += 1
        home_csv = match_team(info.get('home') or '', teams_by_code[code])
        away_csv = match_team(info.get('away') or '', teams_by_code[code])
        if not home_csv or not away_csv:
            skipped['TEAM_UNMATCHED'] = skipped.get('TEAM_UNMATCHED', 0) + 1
            continue
        artifact = models[code]
        season = sorted(artifact['parameters']['season_effects'])[-1]
        proj = project_fixture(artifact,
                               home_team_id=team_id(code, home_csv),
                               away_team_id=team_id(code, away_csv),
                               season=season)
        if proj.distribution is None:
            key = ','.join(proj.reason_codes) or 'PROJECTION_BLOCKED'
            skipped[key] = skipped.get(key, 0) + 1
            continue
        try:
            v = sc.get_match(info['match_id'])
            mk = sc.extract_markets(v)
            time.sleep(0.25)
        except Exception:
            skipped['ODDS_FETCH_FAILED'] = skipped.get('ODDS_FETCH_FAILED', 0) + 1
            continue
        opps = price_fixture(proj.distribution, mk)
        if not opps:
            skipped['NO_VALUE'] = skipped.get('NO_VALUE', 0) + 1
            continue
        market, label, o = max(opps, key=lambda t: t[2]['ev'])
        picks.append({
            'match_id': int(info['match_id']),
            'match': f"{info.get('home')} vs {info.get('away')}",
            'home': info.get('home'), 'away': info.get('away'),
            'league': info.get('league'),
            'start_ts': int(float(info['start_ts'])),
            'market': market, 'pick': label,
            'probability': round(o['probability'], 4),
            'odds': o['odds'],
            'ev': round(o['ev'], 4),
            'conservative_ev': round(o['conservative_ev'], 4),
            'uncertainty_penalty': UNCERTAINTY_PENALTY,
            'fair_odds': round(o['fair_odds'], 3),
            'market_probability': (round(o['market_probability'], 4)
                                   if o['market_probability'] is not None else None),
            'edge_pct': (round(o['probability'] - o['market_probability'], 4)
                         if o['market_probability'] is not None else None),
            'formula_version': FORMULA_VERSION,
            'lambda_source': 'engine-dc-csv',
            'coverage_status': 'full',
            'league_model': code,
            'selection_status': 'watch',
            'decision': 'watch',
            'tier': 'watch',
            'is_top_pick': False,
            'calibrated_prob': None,
            'rank_score': round(o['ev'] * 100, 2),
            'locked': False,
        })
        m['picks'] = [picks[-1]]
        m['qualified_picks'] = [picks[-1]]
        m['info']['coverage_status'] = 'full'

    # 4. atomic writes
    def atomic_write(path, data):
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    ordered = sorted(merged.values(), key=lambda m: float(m['info'].get('start_ts') or 0))
    atomic_write(matches_path, ordered)
    atomic_write(os.path.join(FC_DIR, 'picks.json'), picks)

    config_path = os.path.join(FC_DIR, 'config.json')
    cfg = {}
    try:
        with open(config_path) as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    cfg['formula'] = {'version': FORMULA_VERSION}
    cfg['last_successful_scan_at'] = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
    cfg['last_successful_scan_count'] = scanned
    cfg['last_successful_scan_picks'] = len(picks)
    cfg['last_scan_diagnostics'] = {'skipped': skipped, 'leagues': codes_needed}
    atomic_write(config_path, cfg)

    print(json.dumps({
        'status': 'ok', 'fixtures_future': len(future), 'scanned': scanned,
        'picks': len(picks), 'skipped': skipped,
        'markets': sorted({p['market'] for p in picks}),
        'seconds': round(time.time() - started, 1),
    }, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
