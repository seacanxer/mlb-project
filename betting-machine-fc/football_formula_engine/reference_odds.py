"""Bulk sharp-reference capture from The Odds API (one request per competition).

Pairing is kickoff-scoped: a provider event is attached to a scanned 1xbit
fixture only when the kickoffs agree within ``KICKOFF_TOLERANCE_SECONDS`` and
both team names score as the same club, with a unique best candidate. Home
and away are never swapped. Anything ambiguous stays unmatched: a missing
reference only withholds value picks, while a wrong match would invent edge.
Quotes are recorded in the immutable QuoteJournal under the 1xbit fixture ID,
so the scanner reads them with the same as-of rules.
"""
import difflib
import json
import re
import time
import unicodedata
from urllib.parse import quote, urlencode
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

from .second_source import normalize_event, timestamp

API_BASE = 'https://api.the-odds-api.com/v4/sports/'
KICKOFF_TOLERANCE_SECONDS = 60
MARKETS = 'h2h,totals,spreads'
PAIR_MIN_SCORE = 0.80
PAIR_MIN_MARGIN = 0.15

# The Odds API sport keys for league codes that have a domestic goal model.
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

# Competitions without a validated goal model. They are priced only against
# the sharp reference (reference-only lane) and labelled as such. Keys are
# 1xbit league labels, lower-cased.
REFERENCE_ONLY_COMPETITIONS = {
    'uefa champions league': 'soccer_uefa_champs_league',
    'uefa europa league': 'soccer_uefa_europa_league',
    'uefa conference league': 'soccer_uefa_europa_conference_league',
    'uefa europa conference league': 'soccer_uefa_europa_conference_league',
    'austria. bundesliga': 'soccer_austria_bundesliga',
    'switzerland. super league': 'soccer_switzerland_superleague',
    'denmark. superliga': 'soccer_denmark_superliga',
    'norway. eliteserien': 'soccer_norway_eliteserien',
    'sweden. allsvenskan': 'soccer_sweden_allsvenskan',
    'sweden. superettan': 'soccer_sweden_superettan',
    'finland. veikkausliiga': 'soccer_finland_veikkausliiga',
    'poland. ekstraklasa': 'soccer_poland_ekstraklasa',
    'russia. premier league': 'soccer_russia_premier_league',
    'scotland. premier league': 'soccer_spl',
    'argentina. primera division': 'soccer_argentina_primera_division',
    'brazil. campeonato brasileiro. serie a': 'soccer_brazil_campeonato',
    'chile. primera division': 'soccer_chile_campeonato',
    'china. super league': 'soccer_china_superleague',
    'japan. j-league': 'soccer_japan_j_league',
    'south korea. k league 1': 'soccer_korea_kleague1',
    'saudi arabia. saudi professional league': 'soccer_saudi_arabia_pro_league',
    'usa. mls': 'soccer_usa_mls',
    'australia. a-league': 'soccer_australia_aleague',
    'copa sudamericana': 'soccer_conmebol_copa_sudamericana',
    'copa libertadores': 'soccer_conmebol_copa_libertadores',
}

# 1xbit lists player-proposition markets as pseudo-fixtures in leagues such as
# "England. Premier League. Team vs Player". They are not football matches.
_ARTIFACT_LEAGUE = re.compile(r'\b(team|player)\s+vs\s+(team|player)\b', re.IGNORECASE)


def is_market_artifact(league):
    return bool(_ARTIFACT_LEAGUE.search(league or ''))


def reference_sport_key(league, code=None):
    if code and code in SPORT_KEYS:
        return SPORT_KEYS[code]
    return REFERENCE_ONLY_COMPETITIONS.get((league or '').strip().lower())


# Reviewed provider variants -> one canonical name (applied after normalisation).
ALIASES = {
    'internazionale': 'inter', 'inter milan': 'inter', 'fc internazionale milano': 'inter',
    'internazionale milano': 'inter',
    'rasenballsport leipzig': 'rb leipzig', 'leipzig': 'rb leipzig',
    'sporting lisbon': 'sporting', 'sporting cp': 'sporting', 'sporting clube de portugal': 'sporting',
    'psv eindhoven': 'psv', 'bayern munich': 'bayern', 'bayern munchen': 'bayern',
    'fc bayern munchen': 'bayern',
    'slavia praha': 'slavia prague', 'sk slavia praha': 'slavia prague',
    'sparta praha': 'sparta prague', 'atletico de madrid': 'atletico madrid',
    'club atletico de madrid': 'atletico madrid', 'paris saint germain': 'psg',
    'paris sg': 'psg', 'manchester united': 'man utd', 'man united': 'man utd',
    'manchester city': 'man city', 'tottenham hotspur': 'tottenham', 'spurs': 'tottenham',
    'wolverhampton wanderers': 'wolves', 'nottingham forest': 'nottm forest',
    "nott'm forest": 'nottm forest', 'west bromwich albion': 'west brom',
    'queens park rangers': 'qpr', 'sheffield wednesday': 'sheffield weds',
    'brighton and hove albion': 'brighton', 'newcastle united': 'newcastle',
    'borussia monchengladbach': 'monchengladbach', 'b monchengladbach': 'monchengladbach',
    'borussia dortmund': 'dortmund', 'bayer leverkusen': 'leverkusen',
    'eintracht frankfurt': 'frankfurt', 'olympique lyonnais': 'lyon',
    'olympique de marseille': 'marseille', 'red star belgrade': 'crvena zvezda',
    'fk crvena zvezda': 'crvena zvezda', 'dinamo zagreb': 'gnk dinamo zagreb',
    'red bull salzburg': 'salzburg', 'rb salzburg': 'salzburg',
    'young boys': 'bsc young boys', 'qarabag': 'qarabag agdam', 'karabakh': 'qarabag agdam',
    'ac milan': 'milan', 'as roma': 'roma', 'ss lazio': 'lazio', 'ssc napoli': 'napoli',
}
_JUNK = {'fc', 'cf', 'sc', 'afc', 'ac', 'as', 'rc', 'sk', 'fk', 'kv', 'ssc', 'cp', 'sv', 'bk',
         'if', 'ff', 'cd', 'ud', 'sd', 'calcio', 'club', 'de', 'the', '1', '04', '05', '1899', '1909'}


def normalize_name(name):
    text = unicodedata.normalize('NFKD', name or '')
    text = ''.join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^a-z0-9' ]+", ' ', text.replace('&', ' and '))
    text = ' '.join(text.split())
    text = ALIASES.get(text, text)
    core = ' '.join(token for token in text.split() if token not in _JUNK) or text
    return ALIASES.get(core, core)


def name_score(left, right, same_team=None):
    if same_team is not None and same_team(left, right):
        return 1.0
    a, b = normalize_name(left), normalize_name(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ta, tb = set(a.split()), set(b.split())
    if ta and tb and (ta <= tb or tb <= ta) and max(len(ta), len(tb)) <= 3:
        return 0.9
    return difflib.SequenceMatcher(None, a, b).ratio()


def pair_events(events, fixtures, same_team=None):
    """Pair provider events with fixtures. Returns [(fixture_info, event)]."""
    parsed = []
    for event in events:
        try:
            parsed.append((timestamp(event['commence_time']), event))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    claims = {}
    for info in fixtures:
        scored = []
        for commence, event in parsed:
            if abs(float(info['start_ts']) - commence) > KICKOFF_TOLERANCE_SECONDS:
                continue
            score = min(name_score(info.get('home') or '', event.get('home_team') or '', same_team),
                        name_score(info.get('away') or '', event.get('away_team') or '', same_team))
            scored.append((score, event['id'], event))
        scored.sort(key=lambda item: item[0], reverse=True)
        if not scored or scored[0][0] < PAIR_MIN_SCORE:
            continue
        if len(scored) > 1 and scored[0][0] - scored[1][0] < PAIR_MIN_MARGIN:
            continue
        claims.setdefault(scored[0][1], []).append((info, scored[0][2]))
    # An event claimed by two fixtures is ambiguous for both.
    return [pairs[0] for pairs in claims.values() if len(pairs) == 1]


# Backwards-compatible name used by earlier callers/tests.
def match_events(events, fixtures, resolve):
    return pair_events(events, fixtures, same_team=lambda a, b: bool(resolve(a)) and resolve(a) == resolve(b))


def fetch_league(sport_key, api_key, bookmaker, regions='eu', opener=urlopen):
    query = urlencode({'apiKey': api_key, 'regions': regions, 'bookmakers': bookmaker,
                       'markets': MARKETS, 'oddsFormat': 'decimal'})
    url = API_BASE + quote(sport_key, safe='') + '/odds?' + query
    # Never surface the URL: it contains the credential.
    with opener(url, timeout=25) as response:
        return json.load(response)


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


def fetch_failure(exc):
    """Safe operational diagnosis. Never include URLs, response bodies or keys."""
    status = exc.code if isinstance(exc, HTTPError) else None
    reason = ({401: 'AUTHENTICATION_FAILED', 402: 'PAYMENT_OR_QUOTA_REQUIRED',
               403: 'ACCESS_DENIED', 404: 'SPORT_OR_ENDPOINT_UNAVAILABLE',
               422: 'REQUEST_NOT_SUPPORTED', 429: 'RATE_LIMIT_OR_QUOTA'}.get(status)
              if status is not None else None)
    if reason is None:
        reason = ('PROVIDER_UNAVAILABLE' if status is not None and status >= 500 else
                  'NETWORK_ERROR' if isinstance(exc, URLError) else 'FETCH_ERROR')
    return {'error_type': type(exc).__name__, 'http_status': status,
            'failure_reason': reason, 'retryable': reason in ('NETWORK_ERROR', 'PROVIDER_UNAVAILABLE')}


def capture(fixtures_by_sport, journal, *, api_key, bookmaker, regions='eu',
            opener=urlopen, now=None, same_team=None):
    """Fetch and record reference quotes, keyed by The Odds API sport key.

    ``same_team`` optionally maps sport key -> callable(a, b) asserting two
    names are the same club (e.g. via a league's training-team resolver).
    Returns per-sport diagnostics.
    """
    report = {}
    for sport_key, fixtures in sorted(fixtures_by_sport.items()):
        if not fixtures:
            continue
        try:
            events = fetch_league(sport_key, api_key, bookmaker, regions, opener)
        except Exception as exc:
            report[sport_key] = {'status': 'FETCH_FAILED', **fetch_failure(exc),
                                 'fixtures': len(fixtures), 'requested_markets': MARKETS.split(','),
                                 'unsupported_by_bulk_request': ['btts', 'corners', 'cards']}
            continue
        captured_at = time.time() if now is None else now
        matched, recorded, failed = 0, 0, 0
        pairs = pair_events(events, fixtures, (same_team or {}).get(sport_key))
        for info, event in pairs:
            matched += 1
            try:
                recorded += bool(record_event(info, event, journal, bookmaker, captured_at))
            except Exception:
                failed += 1
        matched_ids = {str(info['match_id']) for info, _ in pairs}
        report[sport_key] = {
            'status': 'CAPTURED', 'events': len(events), 'fixtures': len(fixtures),
            'matched': matched, 'recorded': recorded, 'failed': failed,
            'requested_markets': MARKETS.split(','),
            'unsupported_by_bulk_request': ['btts', 'corners', 'cards'],
            'unmatched': [f"{info.get('home')} vs {info.get('away')}" for info in fixtures
                          if str(info['match_id']) not in matched_ids][:20]}
    return report
