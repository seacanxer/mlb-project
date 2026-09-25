"""League registry: model codes, training files, timezones and score feeds.

Each entry is a :class:`League` tuple laid out as ``(csvs, tz, names, source,
feed)`` so legacy positional readers (``LEAGUES[code][0..2]``) keep working.

``source`` is the provenance of the registered training files:

``football-data``
    Files come from football-data.co.uk (score + odds columns) or from a
    score-only mirror of it.  Only these codes are refreshed through
    ``refresh_scores``.
``dayfeed``
    Files are written by ``scripts/fc-fetch-dayfeed.py`` from a score feed
    (FotMob day feed / ESPN scoreboard).  Scores only - never odds.

``feed`` describes how to locate the league in the upstream score feed:

* ``kind``  - ``fotmob`` or ``espn``
* ``ccode`` - FotMob country code (ignored for ESPN)
* ``names`` - accepted league names; a trailing ``*`` marks a prefix match
* ``slug``  - ESPN sport league slug (ESPN only)
* ``season_start_month`` - first month of a season (default 7 = July-June)
"""
from datetime import datetime, timezone
from typing import NamedTuple, Optional

from .live_training import current_season

DEFAULT_SEASON_START_MONTH = 7
PRIOR_SEASON = '2526'


class League(NamedTuple):
    csvs: list
    tz: str
    names: list
    source: str
    feed: Optional[dict]


def _fd(csvs, tz, names, ccode, feed_names, season_start_month=DEFAULT_SEASON_START_MONTH):
    return League(list(csvs), tz, names, 'football-data',
                  {'kind': 'fotmob', 'ccode': ccode, 'names': list(feed_names),
                   'season_start_month': season_start_month})


def _dayfeed(code, tz, names, ccode, feed_names, season_start_month=DEFAULT_SEASON_START_MONTH):
    csvs = [(f'{code}_{PRIOR_SEASON}_dayfeed.csv', PRIOR_SEASON)]
    return League(csvs, tz, names, 'dayfeed',
                  {'kind': 'fotmob', 'ccode': ccode, 'names': list(feed_names),
                   'season_start_month': season_start_month})


LEAGUES = {
    # football-data.co.uk codes. Registered files keep their provenance; the
    # FotMob feed only backfills seasons football-data does not ship yet.
    'E0': _fd([('E0_2425.csv', '2425'), ('E0_2526.csv', '2526')], 'Europe/London',
              ['England. Premier League'], 'ENG', ['Premier League']),
    'E1': _fd([('E1_2526.csv', '2526')], 'Europe/London', ['England. Championship'],
              'ENG', ['Championship']),
    'E2': _fd([('E2_2526.csv', '2526')], 'Europe/London', ['England. League One'],
              'ENG', ['League One']),
    'E3': _fd([('E3_2526.csv', '2526')], 'Europe/London', ['England. League Two'],
              'ENG', ['League Two']),
    'EC': _fd([('EC_2526.csv', '2526')], 'Europe/London', ['England. National League'],
              'ENG', ['National League']),
    'SP1': _fd([('SP1_2526.csv', '2526')], 'Europe/Madrid', ['Spain. La Liga'],
               'ESP', ['LaLiga']),
    'SP2': _fd([('SP2_2526.csv', '2526')], 'Europe/Madrid', ['Spain. Segunda Division'],
               'ESP', ['LaLiga2']),
    'D1': _fd([('D1_2526.csv', '2526')], 'Europe/Berlin', ['Germany. Bundesliga'],
              'GER', ['Bundesliga']),
    'D2': _fd([('D2_2526.csv', '2526')], 'Europe/Berlin', ['Germany. 2. Bundesliga'],
              'GER', ['2. Bundesliga']),
    'I1': _fd([('I1_2526.csv', '2526')], 'Europe/Rome', ['Italy. Serie A'],
              'ITA', ['Serie A']),
    'I2': _fd([('I2_2526.csv', '2526')], 'Europe/Rome', ['Italy. Serie B'],
              'ITA', ['Serie B']),
    'F1': _fd([('F1_2526.csv', '2526')], 'Europe/Paris', ['France. Ligue 1'],
              'FRA', ['Ligue 1']),
    'F2': _fd([('F2_2526.csv', '2526')], 'Europe/Paris', ['France. Ligue 2'],
              'FRA', ['Ligue 2']),
    'N1': _fd([('N1_2526.csv', '2526')], 'Europe/Amsterdam', ['Netherlands. Eredivisie'],
              'NED', ['Eredivisie']),
    'P1': _fd([('P1_2526.csv', '2526')], 'Europe/Lisbon', ['Portugal. Primeira Liga'],
              'POR', ['Liga Portugal']),
    'B1': _fd([('B1_2526.csv', '2526')], 'Europe/Brussels',
              ['Belgium. First Division A', 'Belgium. Division 1',
               'Belgium. Jupiler League'], 'BEL', ['Belgian Pro League']),
    'T1': _fd([('T1_2526.csv', '2526')], 'Europe/Istanbul',
              ['Turkiye. Super Lig', 'Turkey. Super Lig'], 'TUR', ['Super Lig']),
    'G1': _fd([('G1_2526.csv', '2526')], 'Europe/Athens', ['Greece. Super League'],
              'GRE', ['Super League']),
    # football-data codes are SC0 Premiership, SC1 Championship,
    # SC2 League One and SC3 League Two.
    'SC0': _fd([], 'Europe/London', ['Scotland. Premiership'], 'SCO', ['Premiership']),
    'SC1': _fd([('historical/SC1_2324.csv', '2324'),
                ('historical/SC1_2425.csv', '2425'),
                ('SC1_2526.csv', '2526')], 'Europe/London', ['Scotland. Championship'],
               'SCO', ['Championship']),
    'SC2': _fd([('SC2_2526.csv', '2526')], 'Europe/London', ['Scotland. League One'],
               'SCO', ['League One']),
    'SC3': _fd([('SC3_2526.csv', '2526')], 'Europe/London', ['Scotland. League Two'],
               'SCO', ['League Two']),
}

# Score-feed only leagues: no football-data file exists for these, so the
# registered CSVs are dayfeed lanes written by scripts/fc-fetch-dayfeed.py.
# Values are (timezone, 1xbit names, FotMob country code, FotMob names, start month).
_DAYFEED = {
    'J2': ('Asia/Tokyo', ['Japan. J-League Division 2'], 'JPN', ['J. League 2'], 2),
    'SCOHL': ('Europe/London', ['Scotland. Highland League'], 'SCO',
              ['Highland League'], 7),
    'EPL2': ('Europe/London', ['England. Development League U21'], 'ENG',
             ['Premier League 2'], 7),
    'IRL0': ('Europe/Dublin', ['Ireland. Premier League'], 'IRL',
             ['Premier Division'], 2),
    'IRL1': ('Europe/Dublin', ['Ireland. Division 1'], 'IRL', ['First Division'], 2),
    'NIRP': ('Europe/London', ['Northern Ireland. IFA Premiership'], 'NIR',
             ['Premiership'], 7),
    'D3': ('Europe/Berlin', ['Germany. 3. Liga'], 'GER', ['3. Liga'], 7),
    'GRLB': ('Europe/Berlin', ['Germany. Regionalliga Bayern'], 'GER',
             ['Regionalliga Bayern'], 7),
    'GRLN': ('Europe/Berlin', ['Germany. Regionalliga North'], 'GER',
             ['Regionalliga North'], 7),
    'GRLNE': ('Europe/Berlin', ['Germany. Regionalliga. Nordost',
                                'Germany. Regionalliga Northeast'], 'GER',
              ['Regionalliga Northeast'], 7),
    'GRLSW': ('Europe/Berlin', ['Germany. Regionalliga Sudwest',
                                'Germany. Regionalliga Southwest'], 'GER',
              ['Regionalliga Southwest'], 7),
    'DEN2': ('Europe/Copenhagen', ['Denmark. 2nd Division'], 'DEN',
             ['2. Division'], 7),
    'DEN3': ('Europe/Copenhagen', ['Denmark. 3rd Division'], 'DEN',
             ['3. Division'], 7),
    'FINY': ('Europe/Helsinki', ['Finland. Ykkosliiga'], 'FIN',
             ['Ykkösliiga', 'Ykkosliiga'], 4),
    'USL1': ('America/New_York', ['USA. USL'], 'USA', ['USL Championship'], 2),
    'CANP': ('America/Toronto', ['Canada. Premier League'], 'CAN',
             ['Premier League'], 4),
    'BRASB': ('America/Sao_Paulo', ['Brazil. Campeonato Brasileiro. Serie B'], 'BRA',
              ['Série B', 'Serie B'], 1),
    'ARGBM': ('America/Argentina/Buenos_Aires', ['Argentina. Primera B Metropolitana'],
              'ARG', ['Primera B Metropolitana*'], 1),
    'PRFEF2': ('Europe/Madrid', ['Spain. Primera Division RFEF. Group 2'], 'ESP',
               ['Primera Federación - Group 2', 'Primera Federacion - Group 2'], 7),
    'NOR3': ('Europe/Oslo', ['Norway. Division 3', 'Norway. Division 3. Group 2',
                             'Norway. Division 3. Group 4'], 'NOR',
             ['Norsk Tipping-ligaen*'], 3),
    'MEX1': ('America/Mexico_City', ['Mexico. Liga MX'], 'MEX', ['Liga MX*'], 7),
    'MEX2': ('America/Mexico_City', ['Mexico. Liga de Expansion MX'], 'MEX',
             ['Liga de Expansion MX*'], 7),
    'N2': ('Europe/Amsterdam', ['Netherlands. Eerste Divisie'], 'NED',
           ['Eerste Divisie'], 7),
    'PAR1': ('America/Asuncion', ['Paraguay. Primera Division'], 'PAR',
             ['Division Profesional'], 1),
}
# Deliberately not mapped (verified against the FotMob day feed): the feed
# does not carry these competitions at all, so a mapping would attach a
# different tier to the slate label.
#   'HRV1' Croatia. 1. NL   -> FotMob CRO only lists the top-flight HNL
#   'GHA1' Ghana. Division 1 -> FotMob GHA only lists the top-flight Premier
#                              League; the slate fixture teams are second tier

for _code, (_tz, _names, _ccode, _feed_names, _start_month) in _DAYFEED.items():
    LEAGUES[_code] = _dayfeed(_code, _tz, _names, _ccode, _feed_names, _start_month)

LEAGUE_BY_NAME = {}
for _code, _league in LEAGUES.items():
    for _name in _league.names:
        LEAGUE_BY_NAME[_name.lower()] = _code


def season_label(kickoff_local, start_month=DEFAULT_SEASON_START_MONTH):
    """Season key for a local kickoff date/datetime value."""
    year = kickoff_local.year if kickoff_local.month >= start_month else kickoff_local.year - 1
    return f'{year % 100:02d}{(year + 1) % 100:02d}'


def feed_season_start_month(code):
    league = LEAGUES.get(code)
    if league is None or not league.feed:
        return DEFAULT_SEASON_START_MONTH
    return int(league.feed.get('season_start_month') or DEFAULT_SEASON_START_MONTH)


def current_season_for(code, now):
    """Season key of the live training-file lane for ``code``."""
    league = LEAGUES.get(code)
    if league is None or league.source == 'football-data':
        return current_season(now)
    date = datetime.fromtimestamp(now, timezone.utc)
    return season_label(date, feed_season_start_month(code))


def feed_league_codes(kind=None):
    return sorted(code for code, league in LEAGUES.items()
                  if league.feed and (kind is None or league.feed.get('kind') == kind))


def matches_feed_name(code, *, ccode=None, name=None, pl_name=None):
    """True when a FotMob league element belongs to the configured league."""
    league = LEAGUES.get(code)
    if not league or not league.feed or league.feed.get('kind') != 'fotmob':
        return False
    if ccode is not None and ccode != league.feed.get('ccode'):
        return False
    if name is None:
        return False
    return _name_matches(league.feed.get('names') or [], name, pl_name)


# A prefix pattern must not swallow sibling competitions (Liga MX vs Liga MX
# Femenil, Premier League vs Premier League 2).
NON_TARGET_TOKENS = ('femenil', 'women', 'woman', 'wfc', 'ladies', 'u19', 'u21',
                     'u23', 'youth', 'reserve', 'reserves', 'junior')


def _name_matches(patterns, name, pl_name):
    for pattern in patterns:
        for candidate in (name, pl_name):
            if not candidate:
                continue
            if pattern.endswith('*'):
                prefix = pattern[:-1]
                if not candidate.startswith(prefix):
                    continue
                tail = candidate[len(prefix):].casefold()
                if any(token in tail for token in NON_TARGET_TOKENS):
                    continue
                return True
            elif candidate == pattern:
                return True
    return False
