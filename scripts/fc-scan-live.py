#!/usr/bin/env python3
"""Live FC scan: fixtures + 1xbit odds -> DC projections -> gated picks.

Pipeline (Phase 7 adapter):
  1. scrape 24h fixtures (merged into matches_detailed.json, like
     scripts/fc-scrape-fixtures.py)
  2. for leagues covered by football-data CSVs, fit/load a daily-cached
     Dixon-Coles artifact (betting-machine-fc/models_cache/{CODE}.json)
  3. fetch live odds per fixture from 1xbit, price 1X2/O-U/AH/BTTS with the
     engine payout math, compute EV against the live price
  4. gate (odds >= 1.6, ev >= EV_GATE, conservative_ev >= 0), max 2 value picks
     per match (different markets); operator locks selections into bets.db
  5. atomic writes: picks.json, matches_detailed.json picks merge,
     config.json scan metadata

Run: betting-machine-fc/venv/bin/python scripts/fc-scan-live.py
"""
import difflib
import argparse
import json
import math
import hashlib
import os
import sys
import time
import unicodedata
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FC_DIR = os.path.join(BASE_DIR, 'betting-machine-fc')
sys.path.insert(0, FC_DIR)

import scraper_1xbit as sc  # noqa: E402
import odds_flashscore  # noqa: E402
from football_formula_engine.data import load_football_data_csv, stable_id  # noqa: E402
from football_formula_engine.markets import asian_handicap, btts, match_odds, over_under  # noqa: E402
from football_formula_engine.model import (FitConfig, fit_dixon_coles,
    build_ratio_baseline_artifact, project_fixture)  # noqa: E402
from football_formula_engine.value import expected_value, fair_odds, proportional_no_vig  # noqa: E402
from football_formula_engine.live_quotes import QuoteJournal  # noqa: E402
from football_formula_engine.second_source import collect as collect_second_source  # noqa: E402
from football_formula_engine.catalog import POLICY_VERSION, select_markets, direction_counts  # noqa: E402
from football_formula_engine.live_training import current_season, refresh_scores  # noqa: E402
from football_formula_engine.national_teams import (MODEL_CODE as NATIONAL_CODE,
    senior_competition, load_results as load_national_results,
    resolve_fixture as resolve_national_fixture,
    nonneutral_baseline_coverage)  # noqa: E402

FORMULA_VERSION = 'dc-loglink-time-decay-v1'
UNCERTAINTY_PENALTY = 0.02
EV_GATE = 0.01
ODDS_FLOOR = 1.6
ODDS_CAP = 2.5
MAX_VALUE_PICKS_PER_MATCH = 2
SECOND_PICK_MIN_CEV = 0.02
NATIONAL_MAX_MARKET_GAP = 0.20
WINDOW_HOURS = 24
MODELS_CACHE = os.path.join(FC_DIR, 'models_cache')
MODEL_DATA_INFO = {}
NATIONAL_MODEL_VERSION = 'intl-ratio-nonneutral-v1'

# football-data code -> (csvs [(file, season)], timezone, 1xbit league names)
LEAGUES = {
    'E0': ([('E0_2425.csv', '2425'), ('E0_2526.csv', '2526')], 'Europe/London',
           ['England. Premier League']),
    'E1': ([('E1_2526.csv', '2526')], 'Europe/London', ['England. Championship']),
    'E2': ([('E2_2526.csv', '2526')], 'Europe/London', ['England. League One']),
    'E3': ([('E3_2526.csv', '2526')], 'Europe/London', ['England. League Two']),
    'EC': ([('EC_2526.csv', '2526')], 'Europe/London',
           ['England. National League']),
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
           ['Belgium. First Division A', 'Belgium. Division 1',
            'Belgium. Jupiler League']),
    'T1': ([('T1_2526.csv', '2526')], 'Europe/Istanbul',
           ['Turkiye. Super Lig', 'Turkey. Super Lig']),
    'G1': ([('G1_2526.csv', '2526')], 'Europe/Athens', ['Greece. Super League']),
    # football-data codes are SC0 Premiership, SC1 Championship,
    # SC2 League One and SC3 League Two. SC0 has no local CSV yet.
    'SC1': ([('historical/SC1_2324.csv', '2324'),
             ('historical/SC1_2425.csv', '2425'),
             ('SC1_2526.csv', '2526')], 'Europe/London', ['Scotland. Championship']),
    'SC2': ([('SC2_2526.csv', '2526')], 'Europe/London', ['Scotland. League One']),
    'SC3': ([('SC3_2526.csv', '2526')], 'Europe/London', ['Scotland. League Two']),
}
LEAGUE_BY_NAME = {}
for code, (_csvs, _tz, names) in LEAGUES.items():
    for name in names:
        LEAGUE_BY_NAME[name.lower()] = code


def model_code(league):
    name = (league or '').strip()
    return NATIONAL_CODE if senior_competition(name) else LEAGUE_BY_NAME.get(name.lower())


def national_market_reason(opportunities):
    benchmark = [offer for market, _label, offer in opportunities if market == '1x2']
    if len(benchmark) != 3:
        return 'MARKET_BENCHMARK_UNAVAILABLE'
    if max(abs(offer['probability'] - offer['market_probability'])
           for offer in benchmark) > NATIONAL_MAX_MARKET_GAP:
        return 'MODEL_MARKET_DISAGREEMENT'
    return None

TEAM_ALIASES = {
    # 1xbit -> football-data
    'man utd': 'manchester united', 'manchester utd': 'manchester united',
    'man city': 'manchester city', 'manchester c': 'manchester city',
    'spurs': 'tottenham hotspur', 'tottenham': 'tottenham hotspur',
    'wolves': 'wolverhampton wanderers', 'wolverhampton': 'wolverhampton wanderers',
    'west ham': 'west ham united', 'brighton': 'brighton hove albion',
    'newcastle': 'newcastle united', 'leeds': 'leeds united',
    '1 koln': 'fc koln', 'koln': 'fc koln',
    'borussia monchengladbach': 'm gladbach', 'gladbach': 'm gladbach',
    'paris saint germain': 'paris sg', 'psg': 'paris sg',
    'paris saint germain fc': 'paris sg',
    'inter': 'internazionale milano', 'inter milan': 'internazionale milano',
    'milan': 'ac milan', 'roma': 'as roma', 'lazio': 'ss lazio',
    'napoli': 'ssc napoli', 'verona': 'hellas verona',
    'real sociedad': 'sociedad', 'athletic bilbao': 'athletic club',
    'atletico madrid': 'atletico madrid', 'real betis': 'betis',
    'bayer leverkusen': 'leverkusen', 'bayer 04 leverkusen': 'leverkusen',
    'leipzig': 'rb leipzig', 'rasenballsport leipzig': 'rb leipzig',
    'dortmund': 'borussia dortmund', 'bayern': 'bayern munich',
    'n e c': 'nijmegen', 'nec': 'nijmegen',
    'inverness ct': 'inverness c', 'inverness': 'inverness c',
    'inverness caledonian thistle': 'inverness c',
    'ayr united': 'ayr', 'greenock morton': 'morton',
    'raith rovers': 'raith rvs', "queen's park": 'queens park',
    # extra 1xbit -> football-data (found via TEAM_UNMATCHED)
    'cagliari calcio': 'cagliari', 'angers sco': 'angers',
    'as saint etienne': 'st etienne', 'saint etienne': 'st etienne',
    'usl dunkerque': 'dunkerque', 'ud almeria': 'almeria',
    'fortuna sittard': 'for sittard',
    'vitoria guimaraes': 'v guimaraes',
    'stade brestois 29': 'brest', 'stade brestois': 'brest',
    'stade rennais': 'rennes', 'rc lens': 'lens', 'racing club de lens': 'lens',
    'rc strasbourg': 'strasbourg', 'fc lorient': 'lorient',
    'olympique lyonnais': 'lyon', 'fc nantes': 'nantes',
    'ogc nice': 'nice', 'losc': 'lille', 'lille osc': 'lille',
    'le havre ac': 'le havre', 'havre ac': 'le havre',
    'aj auxerre': 'auxerre', 'psv eindhoven': 'psv',
    'sc heerenveen': 'heerenveen', 'sparta rotterdam': 'sparta',
    'pec zwolle': 'zwolle', 'fc utrecht': 'utrecht',
    'excelsior': 'excelsior', 'telstar': 'telstar',
    'avellino 1912': 'avellino', 'us avellino': 'avellino',
    'citta di palermo': 'palermo', 'calcio padova': 'padova',
    'mantova 1911': 'mantova', 'sampdoria': 'sampdoria',
    'levante ud': 'levante', 'ud las palmas': 'las palmas',
    'rcd espanyol': 'espanyol', 'rayo vallecano': 'rayo vallecano',
    'rayo vallecano de madrid': 'rayo vallecano',
    'fc barcelona': 'barcelona', 'atletico de madrid': 'atletico madrid',
    'real madrid cf': 'real madrid', 'sevilla fc': 'sevilla',
    'gil vicente': 'gil vicente', 'gil vicente fc': 'gil vicente',
    'santa clara': 'santa clara', 'cd santa clara': 'santa clara',
    'fc porto': 'porto', 'sl benfica': 'benfica',
    'sporting cp': 'sporting', 'sc braga': 'braga',
    'vitoria de guimaraes': 'v guimaraes',
    'casa pia ac': 'casa pia', 'estoril praia': 'estoril',
    'fc arouca': 'arouca', 'rio ave': 'rio ave',
    'boavista': 'boavista', 'estrela amadora': 'estrela',
    'farense': 'farense', 'nacional': 'nacional',
    'moreirense': 'moreirense', 'alverca': 'alverca',
    'psv': 'psv', 'ajax amsterdam': 'ajax', 'feyenoord rotterdam': 'feyenoord',
    'az alkmaar': 'az alkmaar', 'fc twente': 'twente',
    'go ahead eagles': 'go ahead', 'nec nijmegen': 'nijmegen',
    'willem ii': 'willem ii', 'heracles almelo': 'heracles',
    'nac breda': 'nac breda', 'fortuna sittard': 'for sittard',
    'hellas verona fc': 'hellas verona', 'atalanta bc': 'atalanta',
    'bologna fc': 'bologna', 'ac monza': 'monza', 'como 1907': 'como',
    'us lecce': 'lecce', 'empoli fc': 'empoli', 'parma calcio': 'parma',
    'torino fc': 'torino', 'udinese calcio': 'udinese',
    'genoa cfc': 'genoa', 'venezia fc': 'venezia',
    'hellas verona': 'hellas verona',
    'fc internazionale milano': 'internazionale milano',
    'juventus fc': 'juventus', 'ss lazio': 'ss lazio',
    'as roma': 'as roma', 'acf fiorentina': 'fiorentina',
    'ssc napoli': 'ssc napoli', 'us sassuolo': 'sassuolo',
    'us salernitana': 'salernitana', 'frosinone calcio': 'frosinone',
    'cagliari calcio': 'cagliari', 'cremonese': 'cremonese',
    'real betis balompie': 'betis', 'real betis sevilla': 'betis',
    'real sociedad de futbol': 'sociedad', 'athletic club bilbao': 'athletic club',
    'athletic bilbao': 'athletic club', 'valencia cf': 'valencia',
    'villarreal cf': 'villarreal', 'getafe cf': 'getafe',
    'ca osasuna': 'osasuna', 'rc celta': 'celta', 'rc celta de vigo': 'celta',
    'deportivo alaves': 'alaves', 'cadiz cf': 'cadiz',
    'real valladolid': 'valladolid', 'girona fc': 'girona',
    'rcd mallorca': 'mallorca', 'rcd espanyol': 'espanyol',
    'leganes': 'leganes', 'cd leganes': 'leganes',
    'real sociedad': 'sociedad', 'real madrid': 'real madrid',
    'rayo vallecano': 'rayo vallecano', 'las palmas': 'las palmas',
    'osasuna': 'osasuna', 'getafe': 'getafe', 'villarreal': 'villarreal',
    'valencia': 'valencia', 'sevilla': 'sevilla', 'betis': 'betis',
    'celta': 'celta', 'alaves': 'alaves', 'mallorca': 'mallorca',
    'girona': 'girona', 'espanyol': 'espanyol', 'valladolid': 'valladolid',
    'levante': 'levante', 'barcelona': 'barcelona',
    'cadiz': 'cadiz', 'athletic club': 'athletic club',
    'sociedad': 'sociedad',
    'st etienne': 'st etienne', 'saint etienne': 'st etienne',
    'as monaco': 'monaco', 'asm monaco': 'monaco',
    'olympique marseille': 'marseille', 'om': 'marseille',
    'olympique lyonnais': 'lyon', 'olympique lyon': 'lyon',
    'fc metz': 'metz', 'rc strasbourg alsace': 'strasbourg',
    'clermont foot': 'clermont', 'toulouse fc': 'toulouse',
    'nimes olympique': 'nimes', 'sc bastia': 'bastia',
    'es troyes ac': 'troyes', 'estac troyes': 'troyes',
    'angers sco': 'angers', 'sco angers': 'angers',
    'borussia monchengladbach': 'm gladbach', 'vfl wolfsburg': 'wolfsburg',
    'eintracht frankfurt': 'eintracht frankfurt', 'vfb stuttgart': 'stuttgart',
    'sc freiburg': 'freiburg', 'tsg hoffenheim': 'hoffenheim',
    'fsv mainz 05': 'mainz', '1 fsv mainz 05': 'mainz',
    'fc augsburg': 'augsburg', 'vfl bochum': 'bochum',
    'borussia dortmund': 'borussia dortmund', 'bayer 04 leverkusen': 'leverkusen',
    'vfl wolfsburg': 'wolfsburg', '1 fc union berlin': 'union berlin',
    'hertha bsc': 'hertha bsc', 'fc koln': 'fc koln',
    'werder bremen': 'werder bremen', 'sv werder bremen': 'werder bremen',
    'hamburger sv': 'hamburg', 'hamburger sv': 'hamburg',
    'st pauli': 'st pauli', 'fc st pauli': 'st pauli',
    'fc heidenheim': 'heidenheim', '1 fc heidenheim': 'heidenheim',
    'holstein kiel': 'holstein kiel', 'sv darmstadt 98': 'darmstadt',
    '1 fc kaiserslautern': 'kaiserslautern', 'hannover 96': 'hannover 96',
    'fc schalke 04': 'schalke', 'fortuna dusseldorf': 'dusseldorf',
    'fortuna dusseldorf': 'dusseldorf', 'sc paderborn 07': 'paderborn',
    '1 fc nurnberg': 'nurnberg', 'eintracht braunschweig': 'braunschweig',
    'sv elversberg': 'elversberg', 'ssv ulm 1846': 'ulm',
    'preussen munster': 'munster', 'karlsruher sc': 'karlsruhe',
    'greuther furth': 'greuther furth', 'spvgg greuther furth': 'greuther furth',
    'fc magdeburg': 'magdeburg', '1 fc magdeburg': 'magdeburg',
    'hertha bsc': 'hertha bsc', 'vfl osnabruck': 'osnabruck',
    'hansa rostock': 'hansa rostock', 'fc hansa rostock': 'hansa rostock',
    'fc st pauli': 'st pauli', 'fc st pauli 1910': 'st pauli',
    'fortuna dusseldorf': 'dusseldorf', 'fortuna dusseldorf 1895': 'dusseldorf',
    'karlsruher sc': 'karlsruhe', 'sc freiburg': 'freiburg',
    'mainz': 'mainz', 'hoffenheim': 'hoffenheim', 'stuttgart': 'stuttgart',
    'wolfsburg': 'wolfsburg', 'augsburg': 'augsburg', 'bochum': 'bochum',
    'union berlin': 'union berlin', 'hertha bsc': 'hertha bsc',
    'freiburg': 'freiburg', 'leverkusen': 'leverkusen',
    'eintracht frankfurt': 'eintracht frankfurt',
    'werder bremen': 'werder bremen', 'st pauli': 'st pauli',
    'heidenheim': 'heidenheim', 'holstein kiel': 'holstein kiel',
    'darmstadt': 'darmstadt', 'kaiserslautern': 'kaiserslautern',
    'hannover 96': 'hannover 96', 'schalke': 'schalke',
    'dusseldorf': 'dusseldorf', 'paderborn': 'paderborn',
    'nurnberg': 'nurnberg', 'braunschweig': 'braunschweig',
    'elversberg': 'elversberg', 'ulm': 'ulm', 'munster': 'munster',
    'greuther furth': 'greuther furth', 'magdeburg': 'magdeburg',
    'osnabruck': 'osnabruck', 'hansa rostock': 'hansa rostock',
    'hamburg': 'hamburg',
    # extra unmatched (1xbit full name -> football-data short)
    '1 heidenheim': 'heidenheim', 'holstein kiel': 'holstein kiel',
    'energie cottbus': 'cottbus', 'vfl osnabruck': 'osnabruck',
    'coventry city': 'coventry', 'manchester united': 'manchester united',
    'sheffield united': 'sheffield united', 'wolverhampton wanderers': 'wolverhampton wanderers',
    'lille osc': 'lille', 'troyes ac': 'troyes',
    'le mans': 'le mans', 'rc lens': 'lens',
    'monza 1912': 'monza', 'sporting clube de portugal': 'sporting',
    'celta vigo': 'celta', 'malaga': 'malaga',
    'getafe cf': 'getafe', 'deportivo de a coruna': 'deportivo',
    'atletico madrid': 'atletico madrid', 'real sociedad': 'sociedad',
    'sporting de gijon': 'gijon', 'eldense': 'eldense',
    'real valladolid': 'valladolid', 'real oviedo': 'oviedo',
    'mallorca': 'mallorca', 'sabadell': 'sabadell',
    'tenerife': 'tenerife', 'leganes': 'leganes',
    'st pauli': 'st pauli', 'fc st pauli': 'st pauli',
    'fc heidenheim': 'heidenheim', '1 fc heidenheim': 'heidenheim',
    'holstein kiel': 'holstein kiel', 'sv darmstadt 98': 'darmstadt',
    '1 fc kaiserslautern': 'kaiserslautern', 'hannover 96': 'hannover 96',
    'fc schalke 04': 'schalke', 'fortuna dusseldorf': 'dusseldorf',
    'sc paderborn 07': 'paderborn', '1 fc nurnberg': 'nurnberg',
    'eintracht braunschweig': 'braunschweig', 'sv elversberg': 'elversberg',
    'ssv ulm 1846': 'ulm', 'preussen munster': 'munster',
    'karlsruher sc': 'karlsruhe', 'greuther furth': 'greuther furth',
    'spvgg greuther furth': 'greuther furth', 'fc magdeburg': 'magdeburg',
    '1 fc magdeburg': 'magdeburg', 'hertha bsc': 'hertha bsc',
    'vfl osnabruck': 'osnabruck', 'hansa rostock': 'hansa rostock',
    'fc hansa rostock': 'hansa rostock', 'fc st pauli 1910': 'st pauli',
    'fortuna dusseldorf 1895': 'dusseldorf', 'karlsruher sc': 'karlsruhe',
    'sc freiburg': 'freiburg', 'mainz': 'mainz', 'hoffenheim': 'hoffenheim',
    'stuttgart': 'stuttgart', 'wolfsburg': 'wolfsburg', 'augsburg': 'augsburg',
    'bochum': 'bochum', 'union berlin': 'union berlin', 'hertha bsc': 'hertha bsc',
    'freiburg': 'freiburg', 'leverkusen': 'leverkusen',
    'eintracht frankfurt': 'eintracht frankfurt', 'werder bremen': 'werder bremen',
    'st pauli': 'st pauli', 'heidenheim': 'heidenheim',
    'holstein kiel': 'holstein kiel', 'darmstadt': 'darmstadt',
    'kaiserslautern': 'kaiserslautern', 'hannover 96': 'hannover 96',
    'schalke': 'schalke', 'dusseldorf': 'dusseldorf', 'paderborn': 'paderborn',
    'nurnberg': 'nurnberg', 'braunschweig': 'braunschweig',
    'elversberg': 'elversberg', 'ulm': 'ulm', 'munster': 'munster',
    'greuther furth': 'greuther furth', 'magdeburg': 'magdeburg',
    'osnabruck': 'osnabruck', 'hansa rostock': 'hansa rostock',
    'hamburg': 'hamburg',
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

    ranked = []
    for cn, t in canon.items():
        if category_locked(n, cn):
            continue
        r = difflib.SequenceMatcher(None, n, cn).ratio()
        ranked.append((r, t))
    ranked.sort(reverse=True)
    if ranked and ranked[0][0] >= 0.86 and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= 0.08):
        return ranked[0][1]
    return None


def quarter(value):
    if not math.isfinite(float(value)):
        return None
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
    csvs = training_files(code, now)
    fingerprint = hashlib.sha256(b''.join(
        Path(FC_DIR, 'data', name).read_bytes()
        for name, _season in csvs if os.path.exists(os.path.join(FC_DIR, 'data', name))
    )).hexdigest()
    if os.path.exists(path):
        try:
            with open(path) as f:
                cached = json.load(f)
            if cached.get('fitted_for_date') == today and cached.get('source_fingerprint') == fingerprint:
                MODEL_DATA_INFO[code] = cached.get('data_info', {})
                return cached['artifact']
        except (OSError, ValueError, KeyError):
            pass
    _configured, tz, _names = LEAGUES[code]
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
    available_results = [m.result_available_at_utc for m in matches
                         if m.result_available_at_utc is not None and m.result_available_at_utc <= now]
    MODEL_DATA_INFO[code] = {'last_result_at': max(available_results, default=0),
                             'source_files': [name for name, _season in csvs]}
    cutoff = int(now)
    try:
        artifact = fit_dixon_coles(matches, cutoff_utc=cutoff, config=FitConfig())
    except Exception as exc:
        print(f'  [{code}] fit failed: {exc}', file=sys.stderr)
        return None
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump({'fitted_for_date': today, 'artifact': artifact,
                   'source_fingerprint': fingerprint, 'data_info': MODEL_DATA_INFO[code]}, f)
    os.replace(tmp, path)
    return artifact


def load_national_model(now):
    """Fit a separate senior-national baseline from known nonneutral results."""
    source = Path(FC_DIR, 'data', 'international_results.csv')
    if not source.exists():
        return None, {}
    os.makedirs(MODELS_CACHE, exist_ok=True)
    path = Path(MODELS_CACHE, f'{NATIONAL_CODE}.json')
    fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()
    today = datetime.fromtimestamp(now, tz=timezone.utc).strftime('%Y-%m-%d')
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding='utf-8'))
            if (cached['fitted_for_date'] == today and cached['source_fingerprint'] == fingerprint
                    and cached.get('model_version') == NATIONAL_MODEL_VERSION):
                MODEL_DATA_INFO[NATIONAL_CODE] = cached['data_info']
                return cached['artifact'], cached['team_counts']
        except (OSError, ValueError, KeyError):
            pass
    matches, neutral_ids, _counts, last_result = load_national_results(source, int(now))
    training, counts = nonneutral_baseline_coverage(matches, neutral_ids)
    if len(training) < 40:
        return None, {}
    try:
        artifact = build_ratio_baseline_artifact(
            training, cutoff_utc=int(now), minimum_team_matches=5)
    except Exception as exc:
        print(f'  [{NATIONAL_CODE}] fit failed: {exc}', file=sys.stderr)
        return None, {}
    info = {'last_result_at': last_result, 'source_files': [source.name],
            'training_matches': len(training), 'neutral_excluded_matches': len(neutral_ids)}
    MODEL_DATA_INFO[NATIONAL_CODE] = info
    payload = {'fitted_for_date': today, 'source_fingerprint': fingerprint,
               'model_version': NATIONAL_MODEL_VERSION,
               'artifact': artifact, 'team_counts': dict(counts), 'data_info': info}
    tmp = path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, path)
    return artifact, counts


def team_id(code, csv_name):
    return 'fd-team-' + stable_id(code, csv_name)


def training_files(code, now=None):
    files = list(LEAGUES[code][0])
    season = current_season(time.time() if now is None else now)
    for name in (f'{code}_{season}_live_scores.csv', f'{code}_{season}.csv'):
        if os.path.exists(os.path.join(FC_DIR, 'data', name)):
            files = [(file, yr) for file, yr in files if yr != season] + [(name, season)]
            break
    return files


def csv_teams(code):
    csvs = training_files(code)
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


def opp(payout, odds, no_vig_probs, *, gated=True):
    """Price a valid offer; value thresholds affect eligibility, not visibility."""
    try:
        odds = float(odds)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(odds) or odds <= 1 or no_vig_probs is None:
        return None
    fo = fair_odds(payout)
    if fo is None:
        return None
    ev = expected_value(payout, odds)
    cev = ev - UNCERTAINTY_PENALTY
    reasons = []
    if not (ODDS_FLOOR <= odds <= ODDS_CAP):
        reasons.append('ODDS_OUTSIDE_VALUE_RANGE')
    if ev < EV_GATE:
        reasons.append('EV_BELOW_VALUE_THRESHOLD')
    if cev < 0:
        reasons.append('CONSERVATIVE_EV_BELOW_THRESHOLD')
    if gated and reasons:
        return None
    return {'odds': odds, 'fair_odds': fo, 'ev': ev, 'conservative_ev': cev,
            'probability': payout.full_win + payout.half_win,
            'effective_win_probability': payout.full_win + 0.5 * payout.half_win,
            'payout': {key: getattr(payout, key) for key in ('full_win', 'half_win', 'push', 'half_loss', 'full_loss')},
            'market_probability': no_vig_probs, 'gate_reasons': reasons}


def price_fixture(dist, mk, *, gated=True):
    """Evaluate both sides of every complete market from the same distribution."""
    out = []
    offer = lambda payout, odds, nv: opp(payout, odds, nv, gated=gated)
    one_x_two = {int(key): value for key, value in (mk.get('odds_1x2') or {}).items() if str(key) in ('1', '2', '3')}
    if all(t in one_x_two for t in (1, 2, 3)):
        try:
            nv = proportional_no_vig([one_x_two[1], one_x_two[2], one_x_two[3]])
        except Exception:
            nv = (None, None, None)
        payouts = match_odds(dist)
        for t, side, label in ((1, 'home', 'Home'), (2, 'draw', 'Draw'), (3, 'away', 'Away')):
            o = offer(payouts[side], one_x_two[t], nv[{1: 0, 2: 1, 3: 2}[t]])
            if o:
                o.update(side=side, line_quarters=None)
                out.append(('1x2', label, o))
    b = mk.get('odds_btts') or {}
    if 'yes' in b and 'no' in b:
        try:
            nv = proportional_no_vig([b['yes'], b['no']])
        except Exception:
            nv = (None, None)
        payouts = btts(dist)
        for side, label, idx in (('yes', 'BTTS Yes', 0), ('no', 'BTTS No', 1)):
            o = offer(payouts[side], b[side], nv[idx])
            if o:
                o.update(side=side, line_quarters=None)
                out.append(('btts', label, o))
    for line, sides in (mk.get('odds_ou') or {}).items():
        sides = {str(key): value for key, value in sides.items()}
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
            o = offer(payout, sides[t], nv[0 if side == 'over' else 1])
            if o:
                o.update(side=side, line_quarters=q)
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
            o = offer(payout, sides[side], nv[idx])
            if o:
                o.update(side=side, line_quarters=q if side == 'home' else -q)
                out.append(('ah', label, o))
    return out


def main(argv=()):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-cache', action='store_true',
                        help='Use fixture IDs from a recent local schedule; live identity and odds are still verified')
    args = parser.parse_args(argv)
    started = time.time()
    # 1. fixtures
    try:
        if args.from_cache:
            cached = json.loads(Path(FC_DIR, 'matches_detailed.json').read_text(encoding='utf-8'))
            rows = []
            for match in cached:
                info = match.get('info') or {}
                if not (0 < started - float(info.get('scraped_at') or 0) <= 21600):
                    continue
                rows.append({'I': info.get('match_id'), 'S': info.get('start_ts'),
                             'O1': info.get('home'), 'O2': info.get('away'), 'L': info.get('league')})
            if not rows:
                raise ValueError('No fixture cache newer than six hours')
        else:
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
                           (model_code(m['info'].get('league')) for m in future)
                           if code is not None})
    for code in codes_needed:
        print(f'  model {code}...', file=sys.stderr)
        if code == NATIONAL_CODE:
            art, team_counts = load_national_model(now)
            if art:
                models[code] = art
                teams_by_code[code] = team_counts
            continue
        # Current-season refresh is bounded and failures are visible; never
        # synthesize new-team ratings from another league's averages.
        refresh_result = refresh_scores(code, os.path.join(FC_DIR, 'data'), now)
        art = load_model(code, now)
        MODEL_DATA_INFO.setdefault(code, {})['refresh'] = refresh_result
        if art:
            models[code] = art
            teams_by_code[code] = csv_teams(code)

    # 3. odds + projection + gate
    picks, scanned, skipped = [], 0, {}
    unavailable_leagues = {}
    unmatched_teams = {}
    journal = QuoteJournal(os.environ.get('FC_QUOTES_DB', os.path.join(FC_DIR, 'live_quotes.db')))
    second_mappings = {}
    mapping_path = os.environ.get('FC_SECOND_MAPPING_PATH')
    second_key = os.environ.get('FC_SECOND_ODDS_API_KEY')
    second_book = os.environ.get('FC_SECOND_BOOKMAKER')
    second_status = 'NOT_CONFIGURED'
    second_captured, second_matched = 0, 0
    if mapping_path and second_key and second_book:
        with open(mapping_path, encoding='utf-8') as handle:
            second_mappings = {str(row['fixture']['match_id']): row for row in json.load(handle)}
        second_status = 'CONFIGURED_NOT_YET_VALIDATED'
    seen_national_fixtures = set()
    for m in sorted(future, key=lambda x: float(x['info']['start_ts'])):
        info = m['info']
        m.update(picks=[], qualified_picks=[], projections=[], market_options=[])
        m['analysis'] = {'status': 'unavailable', 'reason_codes': [],
                         'official_enabled': False, 'official_reason': 'MODEL_NOT_VALIDATED',
                         'policy_version': POLICY_VERSION, 'generated_at': now}
        info['coverage_status'] = 'market_only'
        code = model_code(info.get('league'))
        if not code:
            m['analysis']['reason_codes'] = ['LEAGUE_MODEL_UNAVAILABLE']
            league_name = info.get('league') or 'Unknown league'
            unavailable_leagues[league_name] = unavailable_leagues.get(league_name, 0) + 1
            continue
        national_key = None
        if code == NATIONAL_CODE:
            national_key = (normalize_team_name(info.get('home')),
                            normalize_team_name(info.get('away')),
                            int(float(info['start_ts'])))
            if national_key in seen_national_fixtures:
                skipped['DUPLICATE_FIXTURE'] = skipped.get('DUPLICATE_FIXTURE', 0) + 1
                m['analysis']['reason_codes'] = ['DUPLICATE_FIXTURE']
                continue
        scanned += 1
        # Capture every supported-league fixture before model/team/value filtering.
        try:
            v = sc.get_match(info['match_id'])
            captured_at = time.time()
            if str(v.get('I')) != str(info['match_id']):
                raise ValueError('Provider fixture mismatch')
            if abs(float(v.get('S') or 0) - float(info['start_ts'])) > 60:
                raise ValueError('Provider kickoff changed; refresh fixture')
            if normalize_team_name(v.get('O1')) != normalize_team_name(info.get('home')) or normalize_team_name(v.get('O2')) != normalize_team_name(info.get('away')):
                raise ValueError('Provider team identity changed; refresh fixture')
            mk = sc.extract_markets(v)
            observation = journal.record(info, mk, v, captured_at=captured_at)
            time.sleep(0.25)
        except Exception:
            skipped['QUOTE_CAPTURE_FAILED'] = skipped.get('QUOTE_CAPTURE_FAILED', 0) + 1
            m['analysis']['reason_codes'] = ['QUOTE_CAPTURE_FAILED']
            continue
        secondary = {'status': 'unavailable', 'match_verified': False}
        # Keep the deployed optional comparison non-blocking; primary prices
        # and the immutable journal remain authoritative for decisions.
        try:
            secondary = odds_flashscore.crosscheck(info.get('home'), info.get('away'), info['start_ts'], mk)
            with open(os.path.join(FC_DIR, 'odds_quotes.jsonl'), 'a', encoding='utf-8') as handle:
                handle.write(json.dumps({
                    'captured_at': datetime.fromtimestamp(captured_at, timezone.utc).isoformat(),
                    'provider': '1xbit', 'bookmaker': '1xbit',
                    'match_id': str(info['match_id']), 'home': info.get('home'),
                    'away': info.get('away'), 'league': info.get('league'),
                    'start_ts': int(float(info['start_ts'])), 'markets': mk,
                    'secondary': secondary,
                }, ensure_ascii=False, allow_nan=False) + '\n')
        except Exception:
            skipped['OPTIONAL_CROSSCHECK_FAILED'] = skipped.get('OPTIONAL_CROSSCHECK_FAILED', 0) + 1
        mapping = second_mappings.get(str(info['match_id']))
        if mapping:
            try:
                if abs(float(mapping['fixture']['start_ts']) - float(info['start_ts'])) > 60:
                    raise ValueError('Mapping kickoff is obsolete')
                collect_second_source(mapping, journal, second_key, second_book)
                second_captured += 1
                if journal.compare_sources(info['match_id'], time.time())['status'] == 'MATCHED':
                    second_matched += 1
            except Exception:
                skipped['SECOND_SOURCE_FAILED'] = skipped.get('SECOND_SOURCE_FAILED', 0) + 1
        if code not in models:
            skipped['MODEL_UNAVAILABLE'] = skipped.get('MODEL_UNAVAILABLE', 0) + 1
            m['analysis']['reason_codes'] = ['MODEL_UNAVAILABLE']
            continue
        if code == NATIONAL_CODE:
            resolved = resolve_national_fixture(info.get('home'), info.get('away'), teams_by_code[code])
            home_csv, away_csv = resolved if resolved else (None, None)
        else:
            home_csv = match_team(info.get('home') or '', teams_by_code[code])
            away_csv = match_team(info.get('away') or '', teams_by_code[code])
        if not home_csv or not away_csv:
            reason = 'TEAM_LOW_COVERAGE' if code == NATIONAL_CODE else 'TEAM_COVERAGE_MISSING'
            skipped[reason] = skipped.get(reason, 0) + 1
            m['analysis']['reason_codes'] = [reason]
            for name, matched in ((info.get('home'), home_csv), (info.get('away'), away_csv)):
                if not matched and name:
                    key = f'{code}: {name}'
                    unmatched_teams[key] = unmatched_teams.get(key, 0) + 1
            continue
        artifact = models[code]
        season = ('2026' if code == NATIONAL_CODE else
                  sorted(artifact['parameters']['season_effects'])[-1])
        if code == NATIONAL_CODE:
            home_id, away_id = ('intl-team-' + stable_id(home_csv),
                                'intl-team-' + stable_id(away_csv))
        else:
            home_id, away_id = team_id(code, home_csv), team_id(code, away_csv)
        proj = project_fixture(artifact, home_team_id=home_id,
                               away_team_id=away_id, season=season)
        if proj.distribution is None:
            key = ','.join(proj.reason_codes) or 'PROJECTION_BLOCKED'
            skipped[key] = skipped.get(key, 0) + 1
            m['analysis']['reason_codes'] = list(proj.reason_codes) or ['PROJECTION_BLOCKED']
            continue
        decision_at = time.time()
        if decision_at >= float(info['start_ts']) or decision_at - captured_at > 300:
            skipped['QUOTE_EXPIRED'] = skipped.get('QUOTE_EXPIRED', 0) + 1
            m['analysis']['reason_codes'] = ['QUOTE_EXPIRED']
            continue
        opportunities = price_fixture(proj.distribution, mk, gated=False)
        if code == NATIONAL_CODE:
            reason = national_market_reason(opportunities)
            if reason:
                skipped[reason] = skipped.get(reason, 0) + 1
                info['coverage_status'] = 'shadow'
                m['analysis']['reason_codes'] = [reason]
                m['analysis']['league_model'] = code
                continue
        model_reasons = list(proj.reason_codes)
        if code == NATIONAL_CODE:
            model_reasons.extend(('NATIONAL_BASELINE_UNVALIDATED', 'NEUTRAL_VENUE_UNVERIFIED'))
        last_result = MODEL_DATA_INFO.get(code, {}).get('last_result_at')
        if last_result and now - last_result > 90 * 86400:
            model_reasons.append('STALE_TRAINING_DATA')
        if model_reasons:
            for _market, _label, offer in opportunities:
                offer['gate_reasons'].extend(model_reasons)
        forecasts, value_rows = select_markets(opportunities)
        info['coverage_status'] = 'shadow' if model_reasons else 'full'
        m['analysis'].update(
            status='ready' if forecasts else 'unavailable',
            reason_codes=model_reasons if forecasts else ['COMPLETE_MARKET_UNAVAILABLE'],
            model_data_as_of=last_result,
            model_goals={'home': proj.lambda_home, 'away': proj.lambda_away},
            model_artifact_id=artifact.get('artifact_id'),
            model_training_cutoff=artifact['training']['cutoff_utc'],
            league_model=code, quote_captured_at=captured_at,
            formula_version=artifact.get('formula_version', FORMULA_VERSION),
            direction_counts=direction_counts(forecasts),
        )
        if not value_rows:
            skipped['NO_VALUE'] = skipped.get('NO_VALUE', 0) + 1

        def row_payload(row):
            market, label, o = row
            return {
                'match_id': str(info['match_id']),
                'match': f"{info.get('home')} vs {info.get('away')}",
                'home': info.get('home'), 'away': info.get('away'),
                'league': info.get('league'), 'start_ts': int(float(info['start_ts'])),
                'quote_observation_id': observation['artifact_id'],
                'quote_captured_at': captured_at, 'decision_at': decision_at,
                'uncertainty_status': 'UNAVAILABLE_HEURISTIC_PENALTY_ONLY',
                'market': market, 'pick': label, 'side': o['side'],
                'line_quarters': o['line_quarters'],
                'probability': round(o['probability'], 4),
                'effective_win_probability': round(o['effective_win_probability'], 4),
                'payout': o['payout'], 'odds': o['odds'],
                'ev': round(o['ev'], 4), 'conservative_ev': round(o['conservative_ev'], 4),
                'uncertainty_penalty': UNCERTAINTY_PENALTY,
                'fair_odds': round(o['fair_odds'], 3),
                'market_probability': round(o['market_probability'], 4),
                'edge_pct': round(1 / o['fair_odds'] - o['market_probability'], 4),
                'formula_version': artifact.get('formula_version', FORMULA_VERSION),
                'policy_version': POLICY_VERSION,
                'lambda_source': ('intl-ratio-baseline' if code == NATIONAL_CODE else 'engine-dc-csv'),
                'coverage_status': info['coverage_status'],
                'league_model': code, 'selection_status': 'watch', 'decision': 'watch',
                'tier': 'watch', 'is_top_pick': False, 'calibrated_prob': None,
                'rank_score': round(o['conservative_ev'] * 100, 2), 'locked': False,
                'analysis_status': 'forecast' if o['gate_reasons'] else 'value_candidate',
                'gate_reasons': list(o['gate_reasons']), 'official_eligible': False,
                'quote_provider': '1xbit', 'quote_is_closing': False,
                'secondary_provider': 'flashscore',
                'secondary_status': secondary.get('status', 'unavailable'),
                'secondary_match_verified': secondary.get('match_verified', False),
                'primary_source': '1xbit',
            }

        m['projections'] = [row_payload(row) for row in forecasts]
        if national_key and forecasts:
            seen_national_fixtures.add(national_key)
        m['market_options'] = [row_payload(row) for row in opportunities]
        ranked_value = sorted(value_rows, key=lambda r: r[2]['conservative_ev'], reverse=True)
        kept_value = ranked_value[:1]
        if len(ranked_value) > 1 and ranked_value[1][2]['conservative_ev'] >= SECOND_PICK_MIN_CEV:
            kept_value.append(ranked_value[1])
        for row in kept_value:
            market, _label, o = row
            research = journal.record_research_decision(
                observation['artifact_id'], {'market': market, 'side': o['side'],
                    'line_quarters': o['line_quarters'], 'decimal_odds': o['odds']},
                decision_at=decision_at, policy_id=POLICY_VERSION, model=artifact)
            item = row_payload(row)
            item['research_decision_id'] = research['artifact_id']
            picks.append(item)
            m['qualified_picks'].append(item)
        m['picks'] = list(m['qualified_picks'])

    # 4. atomic writes
    def atomic_write(path, data):
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(tmp, path)

    ordered = sorted(merged.values(), key=lambda m: float(m['info'].get('start_ts') or 0))
    atomic_write(matches_path, ordered)
    atomic_write(os.path.join(FC_DIR, 'picks.json'), picks)

    # A scan only publishes candidates. A deliberate operator lock in
    # /api/fc/locks creates the settlement exposure with frozen odds.
    locked_now = 0

    config_path = os.path.join(FC_DIR, 'config.json')
    cfg = {}
    try:
        with open(config_path) as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    cfg['formula'] = {'version': FORMULA_VERSION}
    cfg['scan_window_hours'] = WINDOW_HOURS
    cfg['last_successful_scan_at'] = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
    cfg['last_successful_scan_count'] = scanned
    cfg['last_successful_scan_picks'] = len(picks)
    cfg['last_scan_diagnostics'] = {'skipped': skipped, 'leagues': codes_needed,
                                    'fixtures_future': len(future),
                                    'modelable_league_fixtures': scanned,
                                    'coverage_verdict': ('NO_SUPPORTED_LEAGUE_24H' if not scanned else
                                                         'VALUE_CHECK_REQUIRED' if not picks else 'VALUE_PICKS_AVAILABLE'),
                                    'league_model_unavailable': sum(unavailable_leagues.values()),
                                    'unavailable_leagues': dict(sorted(unavailable_leagues.items(), key=lambda item: (-item[1], item[0]))),
                                    'unmatched_teams': dict(sorted(unmatched_teams.items(), key=lambda item: (-item[1], item[0]))),
                                    'value_matches': sum(bool(m.get('qualified_picks')) for m in future),
                                    'value_picks': len(picks),
                                    'policy_version': POLICY_VERSION,
                                    'forecast_matches': sum(bool(m.get('projections')) for m in future),
                                    'forecast_count': sum(len(m.get('projections', [])) for m in future),
                                    'official_enabled': False,
                                    'official_reason': 'MODEL_NOT_VALIDATED',
                                    'training_data': MODEL_DATA_INFO,
                                    'second_source': second_status,
                                    'second_source_fixtures_captured': second_captured,
                                    'second_source_fixtures_matched': second_matched}
    atomic_write(config_path, cfg)

    print(json.dumps({
        'status': 'ok', 'fixtures_future': len(future), 'scanned': scanned,
        'picks': len(picks), 'locked': locked_now, 'skipped': skipped,
        'league_model_unavailable': sum(unavailable_leagues.values()),
        'forecasts': sum(len(m.get('projections', [])) for m in future),
        'analyzed_matches': sum(bool(m.get('projections')) for m in future),
        'markets': sorted({p['market'] for p in picks}),
        'seconds': round(time.time() - started, 1),
    }, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
