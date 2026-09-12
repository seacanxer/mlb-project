"""Point-in-time data normalization for the isolated FC v2 engine."""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata
from zoneinfo import ZoneInfo

from .contracts import ContractError, require


def canonical_name(value):
    require(type(value) is str, 'Name must be text')
    result = ' '.join(unicodedata.normalize('NFKC', value).strip().split())
    require(bool(result), 'Name is empty')
    return result


def stable_id(*parts):
    canonical = '\x1f'.join(canonical_name(str(part)).casefold() for part in parts)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:24]


def parse_number(value, *, integer=False, minimum=None):
    if value is None or (type(value) is str and not value.strip()):
        return None
    require(type(value) in (str, int, float) and type(value) is not bool, 'Invalid number')
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ContractError('Invalid number') from exc
    require(math.isfinite(result), 'Nonfinite number')
    if integer:
        require(result.is_integer(), 'Expected integer')
        result = int(result)
    if minimum is not None:
        require(result >= minimum, 'Number below minimum')
    return result


def parse_kickoff(date_value, time_value, timezone_name):
    require(type(date_value) is str, 'Missing match date')
    match_time = time_value.strip() if type(time_value) is str and time_value.strip() else '00:00'
    parsed = None
    for pattern in ('%d/%m/%Y %H:%M', '%d/%m/%y %H:%M'):
        try:
            parsed = datetime.strptime(f'{date_value.strip()} {match_time}', pattern)
            break
        except ValueError:
            continue
    require(parsed is not None, 'Unsupported match date/time')
    offset = re.fullmatch(r'([+-])(\d{2}):(\d{2})', timezone_name) if type(timezone_name) is str else None
    try:
        if timezone_name in ('UTC', 'Etc/UTC'):
            tz = timezone.utc
        elif offset:
            hours, minutes = int(offset.group(2)), int(offset.group(3))
            require(hours <= 23 and minutes <= 59, 'Invalid UTC offset')
            delta = timedelta(hours=hours, minutes=minutes)
            tz = timezone(delta if offset.group(1) == '+' else -delta)
        else:
            tz = ZoneInfo(timezone_name)
        local = parsed.replace(tzinfo=tz)
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError('Timezone database unavailable or invalid; provide a verified UTC offset') from exc
    return int(local.astimezone(timezone.utc).timestamp())


@dataclass(frozen=True)
class NormalizedMatch:
    fixture_id: str
    competition_id: str
    season: str
    home_team_id: str
    away_team_id: str
    home_team_name: str
    away_team_name: str
    kickoff_utc: int
    result_status: str
    home_goals: int | None
    away_goals: int | None
    result_available_at_utc: int | None
    result_availability_basis: str | None
    source: str
    source_file: str
    source_row: int
    raw_sha256: str


@dataclass(frozen=True)
class HistoricalQuote:
    quote_id: str
    fixture_id: str
    market: str
    side: str
    line_quarters: int | None
    decimal_odds: float
    provider: str
    bookmaker: str
    is_closing: bool
    captured_at: int | None
    available_at: int | None
    freshness: str
    provenance: str


@dataclass(frozen=True)
class FixtureSnapshot:
    fixture_id: str
    source_fixture_id: str
    competition_id: str
    competition_name: str
    home_team_id: str
    away_team_id: str
    home_team_name: str
    away_team_name: str
    kickoff_utc: int
    observed_at_utc: int
    source: str
    raw_sha256: str


def _quarter_units(value):
    parsed = parse_number(value)
    if parsed is None:
        return None
    quarters = round(parsed * 4)
    require(abs(parsed * 4 - quarters) <= 1e-8, 'Line is not a quarter increment')
    return quarters


def _raw_hash(row):
    encoded = json.dumps(row, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _epoch_seconds(value, label):
    parsed = parse_number(value, integer=True, minimum=0)
    require(parsed is not None and parsed <= 4102444800, f'Invalid {label} UTC seconds')
    return parsed


def normalize_1xbit_fixture(row, *, observed_at_utc):
    observed = _epoch_seconds(observed_at_utc, 'observed')
    kickoff = _epoch_seconds(row.get('S'), 'kickoff')
    require(kickoff > observed, 'Fixture is not upcoming at observation time')
    source_fixture_id = canonical_name(str(row.get('I') or ''))
    competition = canonical_name(row.get('L'))
    home, away = canonical_name(row.get('O1')), canonical_name(row.get('O2'))
    require(home.casefold() != away.casefold(), 'Teams must differ')
    competition_id = '1xbit-comp-' + stable_id(competition)
    return FixtureSnapshot(
        fixture_id='1xbit-' + stable_id(source_fixture_id), source_fixture_id=source_fixture_id,
        competition_id=competition_id, competition_name=competition,
        home_team_id='1xbit-team-' + stable_id(competition_id, home),
        away_team_id='1xbit-team-' + stable_id(competition_id, away),
        home_team_name=home, away_team_name=away, kickoff_utc=kickoff,
        observed_at_utc=observed, source='1xbit', raw_sha256=_raw_hash(row),
    )


def normalize_quote_snapshot(*, fixture_id, market, side, line, decimal_odds,
                             provider, bookmaker, available_at_utc, captured_at_utc,
                             decision_at_utc, fresh_for_seconds, is_closing=False):
    sides = {'1x2': ('home', 'draw', 'away'), 'ou': ('over', 'under'),
             'ah': ('home', 'away'), 'btts': ('yes', 'no')}
    require(market in sides and side in sides[market], 'Invalid market/side')
    line_quarters = _quarter_units(line)
    require((market in ('ou', 'ah')) == (line_quarters is not None), 'Invalid line presence')
    require(market != 'ou' or line_quarters >= 0, 'Negative total')
    odds = parse_number(decimal_odds)
    require(odds is not None and odds > 1, 'Invalid decimal odds')
    available = _epoch_seconds(available_at_utc, 'available')
    captured = _epoch_seconds(captured_at_utc, 'captured')
    decision = _epoch_seconds(decision_at_utc, 'decision')
    require(available <= captured <= decision, 'Quote violates as-of order')
    require(type(fresh_for_seconds) is int and type(fresh_for_seconds) is not bool
            and 0 <= fresh_for_seconds <= 86400, 'Invalid freshness window')
    for value in (fixture_id, provider, bookmaker):
        require(canonical_name(value) == value, 'Identifier/provider/bookmaker must be canonical')
    require(type(is_closing) is bool, 'Invalid closing flag')
    quote_id = 'quote-' + stable_id(provider, bookmaker, fixture_id, market, side,
                                    line_quarters, captured, odds)
    return HistoricalQuote(
        quote_id, fixture_id, market, side, line_quarters, odds,
        provider, bookmaker, is_closing, captured, available,
        'fresh' if decision - captured <= fresh_for_seconds else 'stale',
        f'{provider}:captured_at={captured}',
    )


def normalize_football_data_row(row, *, competition_id, season, source_file,
                                source_row, timezone_name, result_delay_hours=4,
                                team_namespace=None):
    """Normalize one historical row without inventing quote timestamps."""
    home = canonical_name(row.get('HomeTeam'))
    away = canonical_name(row.get('AwayTeam'))
    require(home.casefold() != away.casefold(), 'Teams must differ')
    require(type(row.get('Time')) is str and bool(row.get('Time').strip()), 'Missing match time')
    require(type(source_row) is int and type(source_row) is not bool and source_row >= 2, 'Invalid source row')
    require(type(result_delay_hours) in (int, float) and type(result_delay_hours) is not bool
            and 0 <= result_delay_hours <= 24, 'Invalid result delay')
    kickoff = parse_kickoff(row.get('Date'), row.get('Time'), timezone_name)
    fixture_id = 'fd-' + stable_id(competition_id, season, kickoff, home, away)
    home_goals = parse_number(row.get('FTHG'), integer=True, minimum=0)
    away_goals = parse_number(row.get('FTAG'), integer=True, minimum=0)
    require((home_goals is None) == (away_goals is None), 'Partial result')
    complete = home_goals is not None
    match = NormalizedMatch(
        fixture_id=fixture_id,
        competition_id=canonical_name(competition_id), season=canonical_name(season),
        home_team_id='fd-team-' + stable_id(team_namespace or competition_id, home),
        away_team_id='fd-team-' + stable_id(team_namespace or competition_id, away),
        home_team_name=home, away_team_name=away, kickoff_utc=kickoff,
        result_status='final' if complete else 'scheduled',
        home_goals=home_goals, away_goals=away_goals,
        result_available_at_utc=kickoff + int(timedelta(hours=result_delay_hours).total_seconds()) if complete else None,
        result_availability_basis=f'kickoff_plus_{result_delay_hours:g}h_assumption' if complete else None,
        source='football-data.co.uk', source_file=Path(source_file).name,
        source_row=int(source_row), raw_sha256=_raw_hash(row),
    )
    return match, _football_data_quotes(row, match)


def _football_data_quotes(row, match):
    specs = [
        ('1x2', 'home', None, 'B365H', False), ('1x2', 'draw', None, 'B365D', False),
        ('1x2', 'away', None, 'B365A', False), ('1x2', 'home', None, 'B365CH', True),
        ('1x2', 'draw', None, 'B365CD', True), ('1x2', 'away', None, 'B365CA', True),
        ('ou', 'over', 10, 'B365>2.5', False), ('ou', 'under', 10, 'B365<2.5', False),
        ('ou', 'over', 10, 'B365C>2.5', True), ('ou', 'under', 10, 'B365C<2.5', True),
    ]
    opening_ah = _quarter_units(row.get('AHh'))
    closing_ah = _quarter_units(row.get('AHCh'))
    if opening_ah is not None:
        specs.extend([('ah', 'home', opening_ah, 'B365AHH', False), ('ah', 'away', -opening_ah, 'B365AHA', False)])
    if closing_ah is not None:
        specs.extend([('ah', 'home', closing_ah, 'B365CAHH', True), ('ah', 'away', -closing_ah, 'B365CAHA', True)])
    quotes = []
    for market, side, line, column, closing in specs:
        odds = parse_number(row.get(column))
        if odds is None:
            continue
        require(odds > 1, f'Invalid decimal odds in {column}')
        quote_id = 'fdq-' + stable_id(match.fixture_id, match.source_row, column, odds)
        quotes.append(HistoricalQuote(
            quote_id, match.fixture_id, market, side, line, odds,
            'football-data.co.uk', 'Bet365', closing,
            None, None, 'unknown', f'{match.source_file}:row={match.source_row}:column={column}',
        ))
    return tuple(quotes)


def load_football_data_csv(path, *, competition_id, season, timezone_name):
    import csv
    path = Path(path)
    matches, quotes = [], []
    seen = set()
    with path.open(newline='', encoding='utf-8-sig') as source:
        reader = csv.DictReader(source)
        require(reader.fieldnames is not None, 'CSV header missing')
        for source_row, row in enumerate(reader, start=2):
            # Football-Data files can contain trailing blank rows.
            if not any(type(value) is str and value.strip() for value in row.values()):
                continue
            match, row_quotes = normalize_football_data_row(
                row, competition_id=competition_id, season=season, source_file=path.name,
                source_row=source_row, timezone_name=timezone_name)
            require(match.fixture_id not in seen, f'Duplicate fixture at row {source_row}')
            seen.add(match.fixture_id)
            matches.append(match); quotes.extend(row_quotes)
    return tuple(matches), tuple(quotes)


def matches_as_of(matches, cutoff_utc):
    require(type(cutoff_utc) is int, 'Cutoff must be UTC seconds')
    return tuple(match for match in matches
                 if match.result_status == 'final' and match.result_available_at_utc is not None
                 and match.result_available_at_utc <= cutoff_utc)


def quotes_as_of(quotes, cutoff_utc):
    require(type(cutoff_utc) is int, 'Cutoff must be UTC seconds')
    return tuple(quote for quote in quotes if quote.available_at is not None and quote.captured_at is not None
                 and quote.available_at <= quote.captured_at <= cutoff_utc)


def dataset_manifest(matches, quotes):
    matches, quotes = tuple(matches), tuple(quotes)
    ordered_matches = sorted((asdict(v) for v in matches), key=lambda v: v['fixture_id'])
    ordered_quotes = sorted((asdict(v) for v in quotes), key=lambda v: v['quote_id'])
    content = json.dumps({'matches': ordered_matches, 'quotes': ordered_quotes}, sort_keys=True,
                         separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    markets = {market: 0 for market in ('1x2', 'ou', 'ah', 'btts')}
    timed = {market: 0 for market in markets}
    for quote in quotes:
        markets[quote.market] += 1
        if quote.available_at is not None and quote.captured_at is not None:
            timed[quote.market] += 1
    return {
        'schema_version': 'fc-dataset-v2', 'sha256': hashlib.sha256(content).hexdigest(),
        'match_count': len(matches), 'final_match_count': sum(m.result_status == 'final' for m in matches),
        'quote_count': len(quotes), 'quote_count_by_market': markets,
        'timed_quote_count_by_market': timed,
        'coverage_exclusions': {
            'quotes_missing_capture_time': sum(markets.values()) - sum(timed.values()),
            'markets_without_quotes': [market for market, count in markets.items() if count == 0],
        },
        'roi_status_by_market': {
            market: ('NOT_EVALUABLE_NO_TIMED_QUOTES' if timed[market] == 0
                     else 'NOT_EVALUABLE_NO_LOCKED_POLICY_RUN') for market in markets
        },
    }
