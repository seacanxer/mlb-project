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
from types import SimpleNamespace
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
from football_formula_engine.markets import PayoutProbabilities, asian_handicap, btts, match_odds, over_under  # noqa: E402
from football_formula_engine.score_matrix import build_score_matrix  # noqa: E402
from football_formula_engine.market_goals import (infer_market_goals,
    blend_goal_projection)  # noqa: E402
from football_formula_engine.secondary_markets import (load_stat_rows as load_secondary_rows,
    project_fixture as project_secondary_fixture)  # noqa: E402
from football_formula_engine.model import (FitConfig, fit_dixon_coles,
    build_ratio_baseline_artifact, project_fixture)  # noqa: E402
from football_formula_engine.value import (effective_win_loss, expected_value, fair_odds,  # noqa: E402
    proportional_no_vig)
from football_formula_engine.market_safety import (anchor_payout, MODEL_WEIGHTS,
    MAX_MODEL_MARKET_GAP, SHRINK_VERSION)  # noqa: E402
from football_formula_engine.live_quotes import QuoteJournal  # noqa: E402
from football_formula_engine.second_source import collect as collect_second_source  # noqa: E402
from football_formula_engine.sharp_reference import (REFERENCE_VERSION,  # noqa: E402
    REFERENCE_MAX_AGE_SECONDS, REFERENCE_CAPTURE_SKEW_SECONDS, MOVEMENT_LOOKBACK_SECONDS, fair_probabilities,
    latest_reference_quotes, reference_snapshot, quotes_to_markets, reference_gate_reasons,
    value_tier)
from football_formula_engine import reference_odds  # noqa: E402
from football_formula_engine.league_tiers import TIER_LABELS, league_tier  # noqa: E402
from football_formula_engine import odds_movement  # noqa: E402
from football_formula_engine.confidence import (compact_options, confidence_tier,  # noqa: E402
    display_markets, score_scenario,
    source_label, tier_hit_rate)
from football_formula_engine.catalog import POLICY_VERSION, select_markets, direction_counts  # noqa: E402
from football_formula_engine.quant import quant_metrics, QUANT_VERSION  # noqa: E402
from football_formula_engine.live_training import current_season, refresh_scores  # noqa: E402
from football_formula_engine.leagues import (LEAGUES, LEAGUE_BY_NAME,  # noqa: E402
    current_season_for)  # noqa: E402
from football_formula_engine.national_teams import (MODEL_CODE as NATIONAL_CODE,
    senior_competition, load_results as load_national_results,
    resolve_fixture as resolve_national_fixture,
    nonneutral_baseline_coverage)  # noqa: E402

FORMULA_VERSION = 'dc-loglink-time-decay-v1'
POLICY_VERSION = POLICY_VERSION + '+quant-v1'
DECISION_FORMULA_VERSION = 'fc-sharp-reference-v5'
# 'sharp_reference' (default): value picks only where the 1xbit price beats a
# sharp book's no-vig fair price. 'model_blend' restores the v4 goal-model EV
# for rollback; the walk-forward replay found it loses with negative CLV.
def _load_env_file():
    """Scans launched by cron or an agent may not inherit the web service env.
    Read FC_* keys from the repo's .env.local/.env without overriding real env."""
    for name in ('.env.local', '.env'):
        path = os.path.join(BASE_DIR, name)
        try:
            with open(path, encoding='utf-8') as handle:
                lines = handle.read().splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip().removeprefix('export ').strip()
            if key.startswith('FC_') and key not in os.environ:
                os.environ[key] = value.strip().strip('"').strip("'")


_load_env_file()
DECISION_MODE = os.environ.get('FC_DECISION_MODE', 'sharp_reference')
REFERENCE_BOOKMAKER = os.environ.get('FC_REFERENCE_BOOKMAKER', 'pinnacle')
# Re-fetch a league's reference before it ages out of REFERENCE_MAX_AGE_SECONDS.
REFERENCE_REFRESH_SECONDS = REFERENCE_CAPTURE_SKEW_SECONDS - 30
# Noise control: value picks only in tier-1/2 competitions, one per fixture,
# at most MAX_VALUE_PICKS_PER_SCAN per scan ranked by tier, high-win, EV.
MAX_VALUE_PICKS_PER_SCAN = 12
MAX_PICK_TIER = 2
# Competitions without a validated goal model (UCL, UEL, ...) or whose domestic
# model cannot project a fixture are priced against the sharp reference only.
# The replay's v5 policy itself used market-implied goals, not the DC model.
REFERENCE_ONLY_FORMULA_VERSION = 'fc-reference-only-v1'
REFERENCE_ONLY_MODEL_STATUS = 'UNVALIDATED_REFERENCE_ONLY'
# Domestic projection failures that may fall back to the reference-only lane.
REFERENCE_FALLBACK_REASONS = ('MODEL_UNAVAILABLE', 'TEAM_COVERAGE_MISSING', 'PROJECTION_BLOCKED')
# Everything else with a complete 1xbit book gets market-implied projections:
# confidence from 1xbit no-vig, never a value pick (no independent price).
MARKET_ONLY_FORMULA_VERSION = 'fc-market-only-v1'
MARKET_ONLY_MODEL_STATUS = 'MARKET_IMPLIED_NO_EDGE'
UNCERTAINTY_PENALTY = 0.02
EV_GATE = 0.01
ODDS_FLOOR = 1.6
ODDS_CAP = 2.5
MAX_VALUE_PICKS_PER_MATCH = 2
SECOND_PICK_MIN_CEV = 0.02
NATIONAL_MAX_MARKET_GAP = 0.20
MARKET_GOAL_WEIGHT = 0.65
WINDOW_HOURS = 24
MODELS_CACHE = os.path.join(FC_DIR, 'models_cache')
MODEL_DATA_INFO = {}
NATIONAL_MODEL_VERSION = 'intl-ratio-nonneutral-v1'


def model_code(league):
    name = (league or '').strip()
    return NATIONAL_CODE if senior_competition(name) else LEAGUE_BY_NAME.get(name.lower())


# market_options is the alternate-line catalog: every book line for both sides,
# none of which is card-shown except the single row the card picks. Writing the
# full row_payload() shape (quant block + match identity + policy metadata) for
# every line inflated matches_detailed.json from ~35 MB to ~400 MB and made the
# Next.js read layer hit its V8 heap limit on JSON.parse -> HTTP 502 with an
# empty board. Keep only the fields the live consumers read, drop match-identity
# keys already carried by match.info, and keep the quant block only where it can
# actually mean something (status == value). Every consumer that needs the whole
# row reads `projections` / `qualified_picks`, which are untouched.
OPTION_PAYLOAD_KEYS = (
    'market', 'pick', 'side', 'line_quarters', 'odds', 'payout', 'probability',
    'effective_win_probability', 'fair_odds', 'ev', 'conservative_ev',
    'uncertainty_penalty', 'gate_reasons', 'is_value', 'quote_captured_at',
    'formula_version', 'lane', 'coverage_status', 'pick_class', 'analysis_status',
    'official_eligible', 'quant',
)


def slim_option_payload(payload):
    """Trim a market_options row to the fields the board/lock/parlay code reads."""
    slim = {}
    for key in OPTION_PAYLOAD_KEYS:
        value = payload.get(key)
        if value is None:
            continue
        if key == 'gate_reasons' and not value:
            continue
        if key == 'quant' and not (isinstance(value, dict) and value.get('status') == 'value'):
            continue
        slim[key] = value
    return slim


def compact_raw(payload):
    """Provider identity plus a digest of the full 1xbit response. Storing the
    whole response (every market of the event) on every scan was the bulk of
    live_quotes.db; nothing reads it back, and the digest still proves what
    was received."""
    try:
        body = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        body = repr(payload)
    keep = {k: payload.get(k) for k in ('I', 'S', 'O1', 'O2', 'L') if isinstance(payload, dict)}
    return {**keep, 'raw_sha256': hashlib.sha256(body.encode('utf-8')).hexdigest(), 'raw_bytes': len(body)}


def slim_projection(payload):
    """Card projection minus bulk the board never reads. The quant block is kept
    in full only for value rows; others keep the cohort stub the ledger groups by."""
    slim = {k: v for k, v in payload.items() if v is not None and k not in PROJECTION_DROP_KEYS}
    quant = payload.get('quant')
    if isinstance(quant, dict) and quant.get('status') != 'value':
        slim['quant'] = {k: quant.get(k) for k in ('schema_version', 'status', 'decision_source')}
    return slim


PROJECTION_DROP_KEYS = frozenset({
    'secondary_provider', 'secondary_status', 'secondary_match_verified', 'primary_source',
    'quote_provider', 'quote_is_closing', 'uncertainty_status', 'selection_status', 'decision',
    'tier', 'is_top_pick', 'calibrated_prob', 'locked', 'official_eligible',
})


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
    'albacete balompie': 'albacete',
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
    # score-feed (FotMob day feed) names: 1xbit -> feed spelling
    'club atletico ituzaingo': 'ituzaingo',
    'londrina': 'londrina ec',
    'havelse': 'tsv havelse',
    'roskilde': 'fc roskilde',
    'helsingor': 'fc helsingør',
    'holbaek': 'holbæk b&i',
    'ktp kotka': 'fc ktp',
    'mikkelin palloilijat': 'mp',
    '1 nurnberg ii': 'nurnberg ii',
    'bayern munich ii': 'bayern munchen ii',
    'bayreuth': 'spvgg bayreuth',
    'buchbach': 'tsv buchbach',
    'memmingen': 'fc memmingen',
    'fsv schoningen': 'schoningen',
    'vfb lubeck': 'lubeck',
    'astoria walldorf': 'fca walldorf',
    'galway': 'galway united',
    'wexford youths': 'wexford',
    'university college dublin': 'ucd',
    'consadole sapporo': 'hokkaido consadole sapporo',
    'atlas guadalajara': 'atlas',
    'correcaminos uat': 'correcaminos de la uat',
    'jaiba brava': 'jaiba brava del tampico madero',
    'dordrecht': 'fc dordrecht',
    'aalesunds ii': 'aalesund 2',
    'rosenborg ii': 'rosenborg 2',
    'atletico madrid ii': 'atletico madrileno',
    'villarreal ii': 'villarreal b',
    'sporting jacksonville': 'sporting jax',
    'tulsa': 'fc tulsa',
    'sportivo luqueno': 'luqueno',
    'club guarani': 'guarani',
    'club nacional asuncion': 'nacional',
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
    tz = LEAGUES[code].tz
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
    season = current_season_for(code, time.time() if now is None else now)
    # Lane priority: football-data live refresh > football-data archive >
    # FotMob day feed > ESPN scoreboard. Only one file per season is used.
    for name in (f'{code}_{season}_live_scores.csv', f'{code}_{season}.csv',
                 f'{code}_{season}_dayfeed.csv', f'{code}_{season}_espn.csv'):
        if os.path.exists(os.path.join(FC_DIR, 'data', name)):
            files = [(file, yr) for file, yr in files if yr != season] + [(name, season)]
            break
    return files


def secondary_stat_files(code):
    """Stat CSVs for corner/card projections.

    The goal model prefers `*_live_scores.csv`, but that lane only carries
    goals (Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG) — no HC/HY/HR/Referee.
    Picking it here starves the count model of every stat column. Instead
    gather every lane that can contribute match statistics: the football-data
    archives (full stats) plus the current-season archive/dayfeed, and skip
    the stat-free live_scores lane entirely.
    """
    if code == NATIONAL_CODE:
        path = os.path.join(FC_DIR, 'data', f'{code}_stat_history.csv')
        return [path] if os.path.exists(path) else []
    season = current_season_for(code, time.time())
    data_dir = os.path.join(FC_DIR, 'data')
    names = [file for file, _season in LEAGUES[code][0]]
    stat_lanes = [
        f'{code}_{season}.csv',
        f'{code}_{season}_dayfeed.csv',
        f'{code}_stat_history.csv',
    ]
    return [os.path.join(data_dir, name) for name in names + stat_lanes
            if os.path.exists(os.path.join(data_dir, name))]


def secondary_analysis(info, cache, goal_projection=None, book=None):
    code = model_code(info.get('league'))
    if code not in LEAGUES and code != NATIONAL_CODE:
        return {'availability': 'C', 'reason': 'NO_HISTORICAL_MATCH_STATS', 'markets': [], 'limited': True}
    if code not in cache:
        aliases = {'Republic of North Macedonia': 'North Macedonia', 'Czech Republic': 'Czechia'}
        normalizer = lambda name: normalize_team_name(aliases.get(name, name)) if code == NATIONAL_CODE else normalize_team_name(name)
        allowed = None if code == NATIONAL_CODE else {normalizer(name) for name in csv_teams(code)}
        cache[code] = load_secondary_rows(secondary_stat_files(code), normalize_team=normalizer, allowed_teams=allowed)
    rows = cache[code]
    teams = {r[side] for r in rows for side in ('home', 'away')}
    aliases = {'Republic of North Macedonia': 'North Macedonia',
               'Czech Republic': 'Czechia'} if code == NATIONAL_CODE else {}
    home_name, away_name = info.get('home') or '', info.get('away') or ''
    home = match_team(aliases.get(home_name, home_name), teams)
    away = match_team(aliases.get(away_name, away_name), teams)
    if not home or not away:
        return {'availability': 'C', 'reason': 'SECONDARY_TEAM_UNMATCHED', 'markets': [], 'limited': True}
    result = project_secondary_fixture(rows, home, away, info['start_ts'],
        goal_projection=goal_projection, referee=info.get('referee'),
        book=book)
    for offer in result.get('markets', []):
        side = offer.get('team') or offer.get('side')
        if side in ('home', 'away'):
            internal = home if side == 'home' else away
            display = home_name if side == 'home' else away_name
            if offer['pick'].startswith(internal):
                offer['pick'] = display + offer['pick'][len(internal):]
        if offer.get('line_source') == 'book':
            offer['quote_captured_at'] = (book or {}).get('captured_at', {}).get(
                'corners' if offer['market'].startswith('corner') else 'cards')
    result['corners_reason'] = None if result.get('corners') else 'INSUFFICIENT_CORNER_HISTORY'
    result['cards_reason'] = None if result.get('cards') else 'INSUFFICIENT_COMPLETE_CARD_HISTORY'
    return result


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


def secondary_pick_payload(info, offer, observation, captured_at, decision_at, code,
                           model_version, referee_status):
    """Wrap a corner/card projection as a pick.

    Without a bookmaker price these are research-only cards (odds null, no EV,
    coverage_status 'projection', never official). When a book price is present
    (1xbit TI=2/8/10 sub-games via extract_secondary_markets) the offer carries
    book_over/book_under and EV is computed against the model probability.
    """
    probability = float(offer.get('probability') or 0.0)
    line = offer.get('line')
    odds = offer.get('book_odds')
    if odds is None:
        price_key = 'book_over' if offer.get('side') == 'over' else 'book_under'
        odds = offer.get(price_key)
    ev = None
    market_probability = None
    if odds is not None:
        try:
            odds = float(odds)
        except (TypeError, ValueError):
            odds = None
    payout = offer.get('payout')
    fair_price = None
    if odds is not None and (not math.isfinite(odds) or odds <= 1):
        odds = None
    if odds is not None and payout:
        distribution = SimpleNamespace(**payout)
        ev = expected_value(distribution, odds)
        fair_price = fair_odds(distribution)
        market_probability = offer.get('p_market_novig')
    priced = odds is not None
    reasons = ['SECONDARY_MODEL_UNVALIDATED']
    if not priced:
        reasons.append('SECONDARY_MARKET_NO_ODDS')
    else:
        if not ODDS_FLOOR <= odds <= ODDS_CAP: reasons.append('ODDS_OUTSIDE_VALUE_RANGE')
        if ev is None or ev < EV_GATE: reasons.append('EV_BELOW_VALUE_THRESHOLD')
        if ev is None or ev - UNCERTAINTY_PENALTY < 0: reasons.append('CONSERVATIVE_EV_BELOW_THRESHOLD')
        if market_probability is None: reasons.append('NOVIG_UNAVAILABLE')
    metrics = (quant_metrics(PayoutProbabilities(**{k: float(v) for k, v in payout.items()}), odds,
        market_no_vig=market_probability, model_probability=probability,
        decision_source='secondary_model', gate_reasons=reasons)
        if priced and payout else None)
    return {
        **({'quant': metrics, 'quant_version': QUANT_VERSION, 'kelly_pct': 0,
            'suggested_stake': None} if metrics else {}),
        'match_id': str(info['match_id']),
        'match': f"{info.get('home')} vs {info.get('away')}",
        'home': info.get('home'), 'away': info.get('away'),
        'league': info.get('league'), 'start_ts': int(float(info['start_ts'])),
        'quote_observation_id': observation['artifact_id'] if observation else None,
        'quote_captured_at': captured_at if priced else None, 'decision_at': decision_at,
        'uncertainty_status': 'SECONDARY_BOOK_PRICED' if priced else 'SECONDARY_MARKET_NO_ODDS',
        'market': offer.get('market') or 'secondary',
        'pick': offer.get('pick') or offer.get('side') or '',
        'side': offer.get('side'),
        # 'home'/'away' for team_cards_ou only; None otherwise. Required by
        # settle_secondary_bet(team=...) — without it a team-cards leg can
        # never be settled (see scripts/fc-settle-live.py).
        'team': offer.get('team'),
        'line_quarters': None if line is None else int(round(float(line) * 4)),
        'probability': round(probability, 4),
        'effective_win_probability': round(payout['full_win']+.5*payout['half_win'], 4) if payout else round(probability, 4),
        'payout': offer.get('payout'),
        'odds': odds,
        'ev': round(ev, 4) if ev is not None else None,
        'conservative_ev': round(ev - UNCERTAINTY_PENALTY, 4) if ev is not None else None,
        'uncertainty_penalty': UNCERTAINTY_PENALTY,
        'fair_odds': round(fair_price, 3) if fair_price else None,
        'market_probability': round(market_probability, 4) if market_probability else None,
        'edge_pct': round(1/fair_price-market_probability, 4) if fair_price and market_probability is not None else None,
        'line_source': offer.get('line_source'),
        'formula_version': model_version,
        'base_formula_version': model_version,
        'policy_version': POLICY_VERSION,
        'lambda_source': 'secondary-count-historical',
        'coverage_status': 'full' if priced else 'projection',
        'league_model': code,
        'selection_status': 'watch', 'decision': 'watch', 'tier': 'watch',
        'is_top_pick': False, 'calibrated_prob': None,
        'rank_score': round((ev if ev is not None else probability) * 100, 2), 'locked': False,
        'analysis_status': 'projection', 'pick_class': 'secondary_display',
        'gate_reasons': reasons,
        'official_eligible': False,
        'quote_provider': '1xbit' if priced else None, 'quote_is_closing': False,
        'secondary_provider': None,
        'secondary_status': 'unavailable',
        'secondary_match_verified': False,
        'primary_source': '1xbit',
        'projection_referee_status': referee_status,
    }


def publish_secondary_picks(m, now):
    """Select display picks without writing scan files or placing bets."""
    picks = []
    info = m['info']
    secondary_result = m.get('analysis', {}).get('secondary_markets') or {}
    if secondary_result.get('availability') != 'B':
        return []
    # Book pricing emits every offered line (over+under per line).
    # Publishing all of them floods the pick list with the same
    # market 40+ times. Keep the one best side per market.
    offers = secondary_result.get('markets', [])
    evaluated = []
    for offer in offers:
        offer = dict(offer)
        price = offer.get('book_odds')
        if price is None:
            price = offer.get('book_over') if offer.get('side') == 'over' else offer.get('book_under')
        offer['book_odds'] = price
        opposite_price = None
        if offer.get('market') in ('corners_ou', 'cards_ou'):
            opposite_price = offer.get('book_under') if offer['side'] == 'over' else offer.get('book_over')
        elif offer.get('market') in ('corner_hdp', 'cards_hdp'):
            opposite_price = next((o.get('book_odds') for o in offers
                if o.get('market') == offer['market'] and o.get('side') != offer['side']
                and o.get('line') == -offer['line']), None)
        if price and opposite_price:
            offer['p_market_novig'] = proportional_no_vig([float(price), float(opposite_price)])[0]
        item = secondary_pick_payload(info, offer, None,
            offer.get('quote_captured_at', m['analysis'].get('secondary_quote_captured_at')), now,
            model_code(info.get('league')), secondary_result.get('model_version'),
            secondary_result.get('referee_status'))
        offer.update(odds=item['odds'], ev=item['ev'], conservative_ev=item['conservative_ev'],
            quote_captured_at=item['quote_captured_at'], gate_reasons=item['gate_reasons'],
            formula_version=item['formula_version'], league_model=item['league_model'])
        if item.get('quant'):
            offer['quant'] = item['quant']
        evaluated.append((offer, item))
    selected = []
    for market in dict.fromkeys(offer['market'] for offer, _ in evaluated):
        rows = [(offer, item) for offer, item in evaluated if offer['market'] == market]
        priced = [(offer, item) for offer, item in rows
                  if item['ev'] is not None and offer.get('p_market_novig') is not None]
        if priced:
            # Display a balanced bookmaker line, never an extreme line selected solely for win probability.
            main = min(priced, key=lambda row: (abs(row[0]['p_market_novig']-.5), abs(row[0].get('line') or 0)))[0]
            home_line = lambda o: -o['line'] if market in ('corner_hdp', 'cards_hdp') and o['side'] == 'away' else o['line']
            candidates = [r for r in priced if home_line(r[0]) == home_line(main)]
            chosen = max(candidates, key=lambda row: row[1]['ev'])
        else:
            chosen = next((row for row in rows if row[1]['odds'] is not None), rows[0])
        selected.append(chosen)
        picks.append(chosen[1])
        m.setdefault('projections', []).append(chosen[1])
        m.setdefault('picks', []).append(chosen[1])
    secondary_result['markets'] = [offer for offer, _ in selected]
    secondary_result['market_options'] = [offer for offer, _ in evaluated]
    secondary_result['market_odds_available'] = any(offer.get('odds') for offer, _ in selected)

    return picks


def opp(payout, odds, no_vig_probs, *, gated=True, market=None, reference=None,
        reference_mode=False, model_confidence=False):
    """Price a valid offer; value thresholds affect eligibility, not visibility.

    In sharp-reference mode ``reference`` is the sharp book's no-vig probability
    for the identical contract. Without it the offer remains a displayed
    forecast and can never become a value pick.
    """
    try:
        odds = float(odds)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(odds) or odds <= 1 or no_vig_probs is None:
        return None
    raw_probability = payout.full_win + payout.half_win
    if reference_mode and reference is not None:
        raw_win, raw_loss = effective_win_loss(payout)
        model_view = raw_win / (raw_win + raw_loss) if model_confidence and raw_win + raw_loss else None
        payout, _ = anchor_payout(payout, reference, 0.0)
        fo = fair_odds(payout)
        if fo is None:
            return None
        ev = expected_value(payout, odds)
        reasons = reference_gate_reasons(odds, ev)
        if gated and reasons:
            return None
        return {'odds': odds, 'fair_odds': fo, 'ev': ev, 'conservative_ev': ev,
                'probability': payout.full_win + payout.half_win,
                'effective_win_probability': payout.full_win + 0.5 * payout.half_win,
                'payout': {key: getattr(payout, key) for key in ('full_win', 'half_win', 'push', 'half_loss', 'full_loss')},
                'market_probability': no_vig_probs, 'reference_probability': reference,
                'reference_bookmaker': REFERENCE_BOOKMAKER, 'gate_reasons': reasons,
                'value_tier': value_tier(reference),
                'confidence': reference, 'confidence_source': 'sharp',
                'market_confidence': no_vig_probs, 'model_confidence': model_view,
                'raw_probability': raw_probability,
                'raw_price_probability': raw_win / (raw_win + raw_loss) if raw_win + raw_loss else None,
                'probability_adjustment': REFERENCE_VERSION,
                'probability_model_weight': 0.0}
    payout, raw_price_probability = anchor_payout(payout, no_vig_probs, MODEL_WEIGHTS.get(market, 1.0))
    fo = fair_odds(payout)
    if fo is None:
        return None
    model_view = None
    if model_confidence:
        win, loss = effective_win_loss(payout)
        model_view = win / (win + loss) if win + loss else None
    ev = expected_value(payout, odds)
    cev = ev - UNCERTAINTY_PENALTY
    reasons = []
    if raw_price_probability is not None and abs(raw_price_probability-no_vig_probs) > MAX_MODEL_MARKET_GAP:
        reasons.append('MODEL_MARKET_DISAGREEMENT')
    if not (ODDS_FLOOR <= odds <= ODDS_CAP):
        reasons.append('ODDS_OUTSIDE_VALUE_RANGE')
    if ev < EV_GATE:
        reasons.append('EV_BELOW_VALUE_THRESHOLD')
    if cev < 0:
        reasons.append('CONSERVATIVE_EV_BELOW_THRESHOLD')
    if reference_mode:
        # No sharp price for this contract: display the forecast, never a pick.
        reasons.append('REFERENCE_UNAVAILABLE')
    if gated and reasons:
        return None
    return {'odds': odds, 'fair_odds': fo, 'ev': ev, 'conservative_ev': cev,
            'probability': payout.full_win + payout.half_win,
            'effective_win_probability': payout.full_win + 0.5 * payout.half_win,
            'payout': {key: getattr(payout, key) for key in ('full_win', 'half_win', 'push', 'half_loss', 'full_loss')},
            'market_probability': no_vig_probs, 'reference_probability': None,
            # Without a sharp price the card uses the goal model pooled with the
            # market when this fixture has one, else 1xbit's own no-vig price.
            'confidence': model_view if model_view is not None else no_vig_probs,
            'confidence_source': 'model' if model_view is not None else 'market',
            'market_confidence': no_vig_probs, 'model_confidence': model_view,
            'gate_reasons': reasons,
            'raw_probability': raw_probability,
            'raw_price_probability': raw_price_probability,
            'probability_adjustment': SHRINK_VERSION if market in MODEL_WEIGHTS else None,
            'probability_model_weight': MODEL_WEIGHTS.get(market, 1.0)}


def price_fixture(dist, mk, *, gated=True, reference_fair=None, model_confidence=False):
    """Evaluate both sides of every complete market from the same distribution.

    ``reference_fair`` maps (market, side, line_quarters) to a sharp no-vig
    probability; passing it (even empty) enables sharp-reference pricing.
    """
    out = []
    reference_mode = reference_fair is not None

    def offer(payout, odds, nv, market, side=None, line_quarters=None):
        reference = (reference_fair or {}).get((market, side, line_quarters))
        return opp(payout, odds, nv, gated=gated, market=market, reference=reference,
                   reference_mode=reference_mode, model_confidence=model_confidence)
    one_x_two = {int(key): value for key, value in (mk.get('odds_1x2') or {}).items() if str(key) in ('1', '2', '3')}
    if all(t in one_x_two for t in (1, 2, 3)):
        try:
            nv = proportional_no_vig([one_x_two[1], one_x_two[2], one_x_two[3]])
        except Exception:
            nv = (None, None, None)
        payouts = match_odds(dist)
        for t, side, label in ((1, 'home', 'Home'), (2, 'draw', 'Draw'), (3, 'away', 'Away')):
            o = offer(payouts[side], one_x_two[t], nv[{1: 0, 2: 1, 3: 2}[t]], '1x2', side)
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
            o = offer(payouts[side], b[side], nv[idx], 'btts', side)
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
            o = offer(payout, sides[t], nv[0 if side == 'over' else 1], 'ou', side, q)
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
            o = offer(payout, sides[side], nv[idx], 'ah', side, q if side == 'home' else -q)
            if o:
                o.update(side=side, line_quarters=q if side == 'home' else -q)
                out.append(('ah', label, o))
    return out


def main(argv=()):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-cache', action='store_true',
                        help='Use fixture IDs from a recent local schedule; live identity and odds are still verified')
    args = parser.parse_args(argv)
    bankroll_units = os.environ.get('FC_BANKROLL_UNITS')
    bankroll_units = float(bankroll_units) if bankroll_units else None
    if bankroll_units is not None and (not math.isfinite(bankroll_units) or bankroll_units <= 0):
        raise ValueError('FC_BANKROLL_UNITS must be finite and positive')
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
    artifact_rows = 0
    for v in rows:
        try:
            mid = str(v.get('I'))
            start = float(v.get('S') or 0)
        except (TypeError, ValueError):
            continue
        if not mid or start <= now:
            continue
        if reference_odds.is_market_artifact(v.get('L')):
            artifact_rows += 1
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
        if start <= now or reference_odds.is_market_artifact(info.get('league')):
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
        # synthesize new-team ratings from another league's averages. Score-feed
        # leagues are rebuilt by scripts/fc-fetch-dayfeed.py instead.
        if LEAGUES[code].source == 'football-data':
            refresh_result = refresh_scores(code, os.path.join(FC_DIR, 'data'), now)
        else:
            refresh_result = {'status': 'skipped', 'season': current_season_for(code, now),
                              'reason': 'NON_FOOTBALL_DATA_SOURCE'}
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
    reference_key = os.environ.get('FC_REFERENCE_ODDS_API_KEY') or second_key
    reference_status = {'mode': DECISION_MODE, 'bookmaker': REFERENCE_BOOKMAKER,
                        'status': 'NOT_CONFIGURED', 'leagues': {}, 'fixtures_priced': 0,
                        'quote_rejections': {}, 'markets_priced': {}}
    reference_enabled = DECISION_MODE == 'sharp_reference' and bool(reference_key)
    coverage = {'fixtures': len(future), 'artifact_rows': artifact_rows, 'model_lane': 0,
                'reference_only_lane': 0, 'reference_fallback': 0, 'market_only_lane': 0,
                'league_unavailable': 0, 'reference_missing': 0, 'duplicates': 0,
                'tier3_skipped': 0, 'tier3_display_only': 0}
    seen_fixture_keys = set()
    fixtures_by_sport, reference_fetched_at = {}, {}

    def same_team_for(sport_key):
        codes = [c for c, key in reference_odds.SPORT_KEYS.items() if key == sport_key and c in teams_by_code]
        if not codes:
            return None
        teams = teams_by_code[codes[0]]
        return lambda a, b: bool(match_team(a, teams)) and match_team(a, teams) == match_team(b, teams)

    def refresh_reference(sport_keys):
        report = reference_odds.capture(
            {k: fixtures_by_sport[k] for k in sport_keys}, journal, api_key=reference_key,
            bookmaker=REFERENCE_BOOKMAKER, regions=os.environ.get('FC_REFERENCE_REGIONS', 'eu'),
            same_team={k: same_team_for(k) for k in sport_keys})
        reference_status['leagues'].update(report)
        states = list(reference_status['leagues'].values())
        captured = sum(s.get('recorded', 0) for s in states)
        failures = any(s['status'] == 'FETCH_FAILED' for s in states)
        reference_status['status'] = ('DEGRADED' if failures and captured else 'UNAVAILABLE' if failures
                                      else 'READY' if captured else 'NO_MATCHES')
        for k in sport_keys:
            reference_fetched_at[k] = time.time()

    if reference_enabled:
        for fixture in future:
            fixture_code = model_code(fixture['info'].get('league'))
            if fixture_code == NATIONAL_CODE:
                continue
            sport_key = reference_odds.reference_sport_key(fixture['info'].get('league'), fixture_code)
            # Value is only allowed in tiers 1-2; do not spend API credits elsewhere.
            if sport_key and league_tier(fixture['info'].get('league'), fixture_code) <= MAX_PICK_TIER:
                fixtures_by_sport.setdefault(sport_key, []).append(fixture['info'])
        refresh_reference(sorted(fixtures_by_sport))
    seen_national_fixtures = set()
    secondary_data = {}
    for m in sorted(future, key=lambda x: float(x['info']['start_ts'])):
        info = m['info']
        m.update(picks=[], qualified_picks=[], projections=[], market_options=[])
        m['analysis'] = {'status': 'unavailable', 'reason_codes': [],
                         'official_enabled': False, 'official_reason': 'MODEL_NOT_VALIDATED',
                         'policy_version': POLICY_VERSION, 'generated_at': now}
        info['coverage_status'] = 'market_only'
        code = model_code(info.get('league'))
        tier = league_tier(info.get('league'), code, national=code == NATIONAL_CODE)
        info['league_tier'] = tier
        if tier > MAX_PICK_TIER and not code:
            # Minor competition without a goal model: not analysed, not stored.
            m['_drop'] = True
            coverage['tier3_skipped'] += 1
            continue
        sport_key = (reference_odds.reference_sport_key(info.get('league'), code)
                     if code != NATIONAL_CODE and tier <= MAX_PICK_TIER else None)
        m['analysis']['secondary_markets'] = secondary_analysis(info, secondary_data)
        try:
            raw_book = sc.extract_secondary_markets(info['match_id']) if m['analysis']['secondary_markets'].get('availability') == 'B' else {}
        except Exception:
            raw_book = {}
        # Scraper keys are 'odds_corners_ou' / 'odds_corner_ah' / 'odds_cards_ou';
        # the model's book contract is 'corners_ou' / 'corner_hdp' / 'cards_ou'.
        secondary_book = {
            'corners_ou': raw_book.get('odds_corners_ou') or {},
            'corner_hdp': raw_book.get('odds_corner_ah') or {},
            'cards_ou': raw_book.get('odds_cards_ou') or {},
            'captured_at': {key: value.get('captured_at') for key, value in
                (raw_book.get('secondary_fetch', {}).get('markets') or {}).items()},
        }
        # Cards book units remain unverified; do not assume points from TI=10.
        m['analysis']['secondary_book'] = secondary_book
        m['analysis']['secondary_markets'] = secondary_analysis(info, secondary_data, book=secondary_book)
        m['analysis']['secondary_fetch'] = raw_book.get('secondary_fetch')
        m['analysis']['secondary_quote_captured_at'] = secondary_book['captured_at'].get('corners')
        preset_lane = None
        if not code and not (sport_key and reference_enabled):
            # No goal model and no sharp market: market-implied projections only.
            preset_lane = 'market_only'
            league_name = info.get('league') or 'Unknown league'
            unavailable_leagues[league_name] = unavailable_leagues.get(league_name, 0) + 1
            coverage['league_unavailable'] += 1
        fixture_key = (normalize_team_name(info.get('home')), normalize_team_name(info.get('away')),
                       int(float(info['start_ts'])) // 60)
        if code != NATIONAL_CODE:
            if fixture_key in seen_fixture_keys:
                coverage['duplicates'] += 1
                skipped['DUPLICATE_FIXTURE'] = skipped.get('DUPLICATE_FIXTURE', 0) + 1
                m['analysis']['reason_codes'] = ['DUPLICATE_FIXTURE']
                continue
            seen_fixture_keys.add(fixture_key)
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
            observation = journal.record(info, mk, compact_raw(v), captured_at=captured_at)
            time.sleep(0.25)
        except Exception:
            skipped['QUOTE_CAPTURE_FAILED'] = skipped.get('QUOTE_CAPTURE_FAILED', 0) + 1
            m['analysis']['reason_codes'] = ['QUOTE_CAPTURE_FAILED']
            continue
        secondary = {'status': 'unavailable', 'match_verified': False}
        # Keep the deployed optional comparison non-blocking; primary prices
        # and the immutable journal remain authoritative for decisions.
        # Market-only fixtures skip it to keep the wider scan light.
        try:
            if preset_lane == 'market_only':
                raise LookupError('skipped for market-only lane')
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
        except LookupError:
            pass
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

        # Lane selection: domestic goal model when it can project this fixture,
        # otherwise the reference-only lane when a sharp competition exists.
        lane, lane_reason, artifact, proj = 'model', None, None, None
        if preset_lane:
            lane = preset_lane
        elif not code:
            lane = 'reference_only'
        elif code not in models:
            lane_reason = 'MODEL_UNAVAILABLE'
        else:
            if code == NATIONAL_CODE:
                resolved = resolve_national_fixture(info.get('home'), info.get('away'), teams_by_code[code])
                home_csv, away_csv = resolved if resolved else (None, None)
            else:
                home_csv = match_team(info.get('home') or '', teams_by_code[code])
                away_csv = match_team(info.get('away') or '', teams_by_code[code])
            if not home_csv or not away_csv:
                lane_reason = 'TEAM_LOW_COVERAGE' if code == NATIONAL_CODE else 'TEAM_COVERAGE_MISSING'
                for name, matched in ((info.get('home'), home_csv), (info.get('away'), away_csv)):
                    if not matched and name:
                        key = f'{code}: {name}'
                        unmatched_teams[key] = unmatched_teams.get(key, 0) + 1
            else:
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
                    lane_reason = ','.join(proj.reason_codes) or 'PROJECTION_BLOCKED'
        if lane_reason:
            # The domestic model cannot project this fixture: use the sharp
            # reference when the competition has one, otherwise market-only.
            skipped[lane_reason] = skipped.get(lane_reason, 0) + 1
            m['analysis']['model_fallback_reason'] = lane_reason
            if sport_key and reference_enabled and code != NATIONAL_CODE:
                lane = 'reference_only'
                coverage['reference_fallback'] += 1
            else:
                lane = 'market_only'

        if sport_key in reference_fetched_at and time.time() - reference_fetched_at[sport_key] > REFERENCE_REFRESH_SECONDS:
            refresh_reference([sport_key])
        decision_at = time.time()
        if decision_at >= float(info['start_ts']) or decision_at - captured_at > 300:
            skipped['QUOTE_EXPIRED'] = skipped.get('QUOTE_EXPIRED', 0) + 1
            m['analysis']['reason_codes'] = ['QUOTE_EXPIRED']
            continue
        reference_fair, reference_quotes = None, {}
        reference_quality = {'quotes': {}, 'fair': {}, 'reason_codes': ['REFERENCE_UNAVAILABLE'], 'rejected_groups': []}
        if DECISION_MODE == 'sharp_reference':
            reference_quality = reference_snapshot(
                journal.as_of(info['match_id'], decision_at,
                              max_age_seconds=REFERENCE_MAX_AGE_SECONDS),
                REFERENCE_BOOKMAKER, decision_at, primary_captured_at=captured_at)
            reference_quotes = reference_quality['quotes']
            reference_fair = reference_quality['fair']
            m['analysis']['reference_quality'] = {
                'reason_codes': reference_quality['reason_codes'],
                'rejected_groups': reference_quality['rejected_groups']}
            for rejected in reference_quality['rejected_groups']:
                reason = rejected['reason']
                reference_status['quote_rejections'][reason] = reference_status['quote_rejections'].get(reason, 0)+1
            for market, _side, _line in reference_fair:
                reference_status['markets_priced'][market] = reference_status['markets_priced'].get(market, 0)+1
            reference_status['fixtures_priced'] += bool(reference_fair)
        # Odds movement: first vs latest complete market per bookmaker from the journal.
        history = journal.as_of(info['match_id'], decision_at, max_age_seconds=MOVEMENT_LOOKBACK_SECONDS)
        reference_series = odds_movement.movement_series(history, REFERENCE_BOOKMAKER)
        primary_series = odds_movement.movement_series(history, '1xbit')

        if lane == 'reference_only' and not reference_fair:
            coverage['reference_missing'] += 1
            skipped['REFERENCE_UNAVAILABLE'] = skipped.get('REFERENCE_UNAVAILABLE', 0) + 1
            lane = 'market_only'
        coverage[{'model': 'model_lane', 'reference_only': 'reference_only_lane',
                  'market_only': 'market_only_lane'}[lane]] += 1

        if lane == 'market_only':
            market_goals = infer_market_goals(mk)
            if market_goals is None:
                skipped['COMPLETE_MARKET_UNAVAILABLE'] = skipped.get('COMPLETE_MARKET_UNAVAILABLE', 0) + 1
                m['analysis']['reason_codes'] = ['COMPLETE_MARKET_UNAVAILABLE']
                continue
            blended_home, blended_away = market_goals['home'], market_goals['away']
            raw_goals = None
            model_reasons = ['MARKET_ONLY_NO_REFERENCE']
            decision_mode = 'market_only'
            formula_version = MARKET_ONLY_FORMULA_VERSION
            model_status = MARKET_ONLY_MODEL_STATUS
            league_model = 'MARKET'
            lambda_source = '1xbit-implied-goals'
            pick_class = 'none'
        elif lane == 'reference_only':
            # Score shape from the sharp book's own implied goals; 1xbit as fallback.
            market_goals = (infer_market_goals(quotes_to_markets(reference_quotes))
                            or infer_market_goals(mk))
            if market_goals is None:
                skipped['COMPLETE_MARKET_UNAVAILABLE'] = skipped.get('COMPLETE_MARKET_UNAVAILABLE', 0) + 1
                m['analysis']['reason_codes'] = ['COMPLETE_MARKET_UNAVAILABLE']
                continue
            blended_home, blended_away = market_goals['home'], market_goals['away']
            raw_goals = None
            model_reasons = []
            decision_mode = 'reference_only'
            formula_version = REFERENCE_ONLY_FORMULA_VERSION
            model_status = REFERENCE_ONLY_MODEL_STATUS
            league_model = f'REF:{sport_key}'
            lambda_source = 'sharp-reference-implied-goals'
            pick_class = 'reference_only'
        else:
            market_goals = infer_market_goals(mk)
            blended_home, blended_away = blend_goal_projection(
                proj.lambda_home, proj.lambda_away, market_goals,
                market_weight=MARKET_GOAL_WEIGHT)
            raw_goals = {'home': proj.lambda_home, 'away': proj.lambda_away}
            model_reasons = list(proj.reason_codes)
            if code == NATIONAL_CODE:
                model_reasons.extend(('NATIONAL_BASELINE_UNVALIDATED', 'NEUTRAL_VENUE_UNVERIFIED'))
            last_result = MODEL_DATA_INFO.get(code, {}).get('last_result_at')
            if last_result and now - last_result > 90 * 86400:
                model_reasons.append('STALE_TRAINING_DATA')
            if tier > MAX_PICK_TIER:
                # Minor league with a domestic model: projections only, never value.
                model_reasons.append('LEAGUE_TIER_DISPLAY_ONLY')
                coverage['tier3_display_only'] += 1
            decision_mode = DECISION_MODE
            formula_version = DECISION_FORMULA_VERSION
            model_status = 'DC_MODEL_UNVALIDATED'
            league_model = code
            lambda_source = 'historical-market-geometric-pool'
            pick_class = 'value_v5' if DECISION_MODE == 'sharp_reference' else 'value_model_blend'
        # The market component already represents low-score pricing, so do not
        # apply the historical Dixon-Coles rho a second time after pooling.
        decision_distribution = build_score_matrix(blended_home, blended_away, 0.0)
        opportunities = price_fixture(decision_distribution, mk, gated=False,
                                      reference_fair=reference_fair,
                                      model_confidence=(lane == 'model'))
        for _market, _label, o in opportunities:
            odds_movement.annotate(o, (_market, o['side'], o['line_quarters']), reference_series, primary_series)
        m['analysis']['secondary_markets'] = secondary_analysis(info, secondary_data,
            {'home': blended_home, 'away': blended_away}, book=secondary_book)
        if code == NATIONAL_CODE and lane == 'model':
            reason = national_market_reason(opportunities)
            if reason:
                skipped[reason] = skipped.get(reason, 0) + 1
                info['coverage_status'] = 'shadow'
                m['analysis']['reason_codes'] = [reason]
                m['analysis']['league_model'] = code
                continue
        if model_reasons:
            for _market, _label, offer in opportunities:
                offer['gate_reasons'].extend(model_reasons)
        _value_forecasts, value_rows = select_markets(opportunities)
        # Quant is calculated after all model/direction gates. These are
        # recommendations only; the settlement ledger continues flat 1u.
        for market, _label, offer in opportunities:
            evidence = reference_quotes.get((market, offer['side'], offer['line_quarters']))
            offer['quant'] = quant_metrics(PayoutProbabilities(**offer['payout']), offer['odds'],
                market_no_vig=offer.get('market_probability'),
                model_probability=offer.get('raw_probability') if lane == 'model' else None,
                reference_probability=offer.get('reference_probability'), reference_evidence=evidence,
                decision_source=offer.get('confidence_source', 'model'),
                gate_reasons=offer['gate_reasons'], bankroll_units=bankroll_units)
        # A validated quote is now necessary for actionable value in every
        # decision mode; the old model_blend remains a projection-only fallback.
        value_rows = [row for row in value_rows if row[2]['quant']['status'] == 'value']
        # Cards always show every market's most likely side with a confidence
        # tier; value is a separate flag, never a condition for display.
        forecasts = display_markets(opportunities)
        info['coverage_status'] = (lane if lane != 'model' else 'shadow' if model_reasons else 'full')
        no_edge = 'REFERENCE_NO_EDGE' if lane == 'reference_only' else 'NO_VALUE_EDGE'
        m['analysis'].update(
            status='ready' if forecasts else 'unavailable',
            reason_codes=(list(model_reasons) if model_reasons else
                          [] if value_rows else
                          [no_edge] if forecasts else ['COMPLETE_MARKET_UNAVAILABLE']),
            lane=lane, model_status=model_status, decision_mode=decision_mode,
            reference_sport_key=sport_key,
            model_data_as_of=MODEL_DATA_INFO.get(code, {}).get('last_result_at') if lane == 'model' else None,
            model_goals={'home': blended_home, 'away': blended_away},
            raw_model_goals=raw_goals,
            market_goal_anchor=market_goals,
            goal_blend=({'market_weight': MARKET_GOAL_WEIGHT, 'method': 'geometric_pool_v1'}
                        if lane == 'model' else {'market_weight': 1.0, 'method': 'sharp_reference_implied'}),
            model_artifact_id=artifact.get('artifact_id') if artifact else None,
            model_training_cutoff=artifact['training']['cutoff_utc'] if artifact else None,
            league_model=league_model, quote_captured_at=captured_at,
            formula_version=formula_version,
            base_formula_version=artifact.get('formula_version', FORMULA_VERSION) if artifact else None,
            direction_counts=direction_counts(forecasts),
            scenario=score_scenario(decision_distribution),
        )
        if not value_rows:
            skipped['NO_VALUE'] = skipped.get('NO_VALUE', 0) + 1

        def row_payload(row, row_class):
            market, label, o = row
            return {
                'match_id': str(info['match_id']),
                'match': f"{info.get('home')} vs {info.get('away')}",
                'home': info.get('home'), 'away': info.get('away'),
                'league': info.get('league'), 'start_ts': int(float(info['start_ts'])),
                'quote_observation_id': observation['artifact_id'] if observation else None,
                'quote_captured_at': captured_at, 'decision_at': decision_at,
                'uncertainty_status': 'UNAVAILABLE_HEURISTIC_PENALTY_ONLY',
                'market': market, 'pick': label, 'side': o['side'],
                'raw_probability': o.get('raw_probability'),
                'probability_adjustment': o.get('probability_adjustment'),
                'raw_price_probability': o.get('raw_price_probability'),
                'probability_model_weight': o.get('probability_model_weight'),
                'line_quarters': o['line_quarters'],
                'probability': round(o['probability'], 4),
                'effective_win_probability': round(o['effective_win_probability'], 4),
                'payout': o['payout'], 'odds': o['odds'],
                'quant': o['quant'], 'quant_version': QUANT_VERSION,
                'kelly_pct': 100*o['quant']['kelly']['recommended_fraction'],
                'suggested_stake': o['quant']['kelly']['recommended_units'],
                'ev': round(o['ev'], 4), 'conservative_ev': round(o['conservative_ev'], 4),
                'uncertainty_penalty': UNCERTAINTY_PENALTY,
                'fair_odds': round(o['fair_odds'], 3),
                'market_probability': round(o['market_probability'], 4),
                'reference_probability': (round(o['reference_probability'], 4)
                                          if o.get('reference_probability') is not None else None),
                'reference_bookmaker': o.get('reference_bookmaker'),
                'value_tier': o.get('value_tier'),
                'reference_open_probability': (round(o['reference_open_probability'], 4)
                                               if o.get('reference_open_probability') is not None else None),
                'reference_move': (round(o['reference_move'], 4)
                                   if o.get('reference_move') is not None else None),
                'primary_open_probability': (round(o['primary_open_probability'], 4)
                                             if o.get('primary_open_probability') is not None else None),
                'primary_move': (round(o['primary_move'], 4) if o.get('primary_move') is not None else None),
                'movement_signal': o.get('movement_signal'),
                'movement_label': odds_movement.SIGNAL_LABELS.get(o.get('movement_signal')),
                'movement_span_minutes': o.get('movement_span_minutes'),
                'movement_snapshots': o.get('movement_snapshots'),
                'league_tier': tier, 'league_tier_label': TIER_LABELS[tier],
                'decision_mode': decision_mode, 'model_status': model_status,
                'pick_class': row_class, 'lane': lane,
                'display_status': o.get('display_status'),
                'main_line_confidence': (round(o['main_line_confidence'], 4)
                                         if o.get('main_line_confidence') is not None else None),
                'confidence': (round(o['confidence'], 4) if o.get('confidence') is not None else None),
                'confidence_source': o.get('confidence_source'),
                'confidence_tier': confidence_tier(o.get('confidence')),
                'confidence_label': source_label(o.get('confidence_source'), national=code == NATIONAL_CODE),
                # Aggregate replay tiers do not validate this fixture/source/
                # line cohort. Prospective cohort metrics are reported separately.
                'tier_hit_rate': None,
                'calibration_cohort_status': 'pending_prospective_validation',
                'market_confidence': (round(o['market_confidence'], 4)
                                      if o.get('market_confidence') is not None else None),
                'model_confidence': (round(o['model_confidence'], 4)
                                     if o.get('model_confidence') is not None else None),
                'is_value': o['quant']['status'] == 'value',
                'edge_pct': round(1 / o['fair_odds'] - o['market_probability'], 4),
                'formula_version': formula_version,
                'base_formula_version': (artifact.get('formula_version', FORMULA_VERSION)
                                         if artifact else None),
                'policy_version': POLICY_VERSION,
                'lambda_source': lambda_source,
                'coverage_status': info['coverage_status'],
                'league_model': league_model, 'selection_status': 'watch', 'decision': 'watch',
                'tier': 'watch', 'is_top_pick': False, 'calibrated_prob': None,
                'rank_score': round(o['conservative_ev'] * 100, 2), 'locked': False,
                'analysis_status': 'value_candidate' if o['quant']['status'] == 'value' else 'forecast',
                'gate_reasons': list(o['gate_reasons']), 'official_eligible': False,
                'quote_provider': '1xbit', 'quote_is_closing': False,
                'secondary_provider': 'flashscore',
                'secondary_status': secondary.get('status', 'unavailable'),
                'secondary_match_verified': secondary.get('match_verified', False),
                'primary_source': '1xbit',
            }

        m['projections'] = [slim_projection(row_payload(row, 'forecast')) for row in forecasts]
        if national_key and forecasts:
            seen_national_fixtures.add(national_key)
        m['market_options'] = [slim_option_payload(row_payload(row, 'market_option'))
                               for row in compact_options(opportunities)]
        # High-win tier first, then expected value.
        # High-win first, then movement (sharp move toward the side, soft book
        # lagging, ranks above a move against it), then expected value.
        ranked_value = sorted(value_rows, key=lambda r: (
            r[2].get('value_tier') != 'high_win',
            odds_movement.SIGNAL_RANK.get(r[2].get('movement_signal'), 3),
            -r[2]['conservative_ev']))
        # One value pick per fixture: correlated second picks double the risk.
        kept_value = ranked_value[:1]
        for row in kept_value:
            market, _label, o = row
            research = journal.record_research_decision(
                observation['artifact_id'], {'market': market, 'side': o['side'],
                    'line_quarters': o['line_quarters'], 'decimal_odds': o['odds']},
                decision_at=decision_at, policy_id=POLICY_VERSION,
                model={**(artifact or {}), 'lane': lane, 'formula_version': formula_version,
                       'reference_bookmaker': REFERENCE_BOOKMAKER})
            item = row_payload(row, pick_class)
            item['research_decision_id'] = research['artifact_id']
            item['research_entry_contract'] = research['contract']
            item['research_observation_id'] = research['observation_id']
            item['research_decision_at'] = research['decision_at']
            picks.append(item)
            m['qualified_picks'].append(item)
        m['picks'] = list(m['qualified_picks'])

    # Corner/card projections stay on the match card (tier 1-2 only); they are
    # unvalidated display rows and no longer flood the pick list.
    for m in merged.values():
        if not m.get('_drop') and (m.get('info') or {}).get('league_tier', 3) <= MAX_PICK_TIER:
            publish_secondary_picks(m, now)

    # 4. Keep one highest-probability pick per match and market.
    deduped = {}
    for item in picks:
        key = (str(item.get('match_id') or item.get('match')), str(item.get('market')))
        prior = deduped.get(key)
        if prior is None or float(item.get('probability') or 0) > float(prior.get('probability') or 0):
            deduped[key] = item
    picks = list(deduped.values())
    # Rank and cap: big competitions first, then high-win tier, then EV.
    picks.sort(key=lambda item: (int(item.get('league_tier') or 3),
                                 item.get('value_tier') != 'high_win',
                                 odds_movement.SIGNAL_RANK.get(item.get('movement_signal'), 3),
                                 -float(item.get('ev') or 0)))
    capped = len(picks) - MAX_VALUE_PICKS_PER_SCAN
    picks = picks[:MAX_VALUE_PICKS_PER_SCAN]
    coverage['value_picks_capped'] = max(capped, 0)

    # 5. atomic writes
    def atomic_write(path, data, compact=False):
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            if compact:
                json.dump(data, f, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
            else:
                json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(tmp, path)

    ordered = sorted((m for m in merged.values() if not m.get('_drop')),
                     key=lambda m: float(m['info'].get('start_ts') or 0))
    atomic_write(matches_path, ordered, compact=True)
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
                                    'second_source_fixtures_matched': second_matched,
                                    'decision_mode': DECISION_MODE,
                                    'decision_formula_version': DECISION_FORMULA_VERSION,
                                    'sharp_reference': reference_status,
                                    'coverage': coverage}
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
