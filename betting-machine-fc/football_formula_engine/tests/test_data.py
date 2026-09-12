from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
from football_formula_engine.contracts import ContractError
from football_formula_engine.data import (dataset_manifest, load_football_data_csv, matches_as_of,
                                          normalize_1xbit_fixture, normalize_football_data_row,
                                          normalize_quote_snapshot, quotes_as_of)


ROW = {
    'Date': '15/08/2025', 'Time': '20:00', 'HomeTeam': ' Liverpool ', 'AwayTeam': 'Bournemouth',
    'FTHG': '4', 'FTAG': '2', 'B365H': '1.3', 'B365D': '6', 'B365A': '8.5',
    'B365CH': '1.29', 'B365CD': '6.25', 'B365CA': '9',
    'B365>2.5': '1.36', 'B365<2.5': '3.2', 'B365C>2.5': '1.36', 'B365C<2.5': '3.2',
    'AHh': '-1.5', 'B365AHH': '1.83', 'B365AHA': '2.03',
    'AHCh': '-1.75', 'B365CAHH': '2.03', 'B365CAHA': '1.78',
}


def normalize(row=ROW):
    return normalize_football_data_row(row, competition_id='E0', season='2526',
                                      source_file='E0_2526.csv', source_row=2,
                                      timezone_name='+01:00')


def test_historical_row_preserves_opening_closing_and_signed_lines():
    match, quotes = normalize()
    assert match.home_team_name == 'Liverpool'
    assert match.result_status == 'final'
    assert match.kickoff_utc == int(datetime(2025, 8, 15, 19, tzinfo=timezone.utc).timestamp())
    assert match.result_available_at_utc == match.kickoff_utc + 4 * 3600
    assert match.result_availability_basis == 'kickoff_plus_4h_assumption'
    assert len(quotes) == 14
    assert {(q.side, q.line_quarters, q.is_closing) for q in quotes if q.market == 'ah'} == {
        ('home', -6, False), ('away', 6, False), ('home', -7, True), ('away', 7, True),
    }
    assert all(q.captured_at is None and q.freshness == 'unknown' for q in quotes)
    assert all(q.provider == 'football-data.co.uk' and q.bookmaker == 'Bet365' for q in quotes)
    assert all('column=' in q.provenance for q in quotes)


def test_as_of_never_uses_result_or_quote_early():
    match, quotes = normalize()
    assert matches_as_of([match], match.result_available_at_utc - 1) == ()
    assert matches_as_of([match], match.result_available_at_utc) == (match,)
    assert quotes_as_of(quotes, match.kickoff_utc) == ()
    timed = replace(quotes[0], available_at=100, captured_at=110)
    assert quotes_as_of([timed], 109) == ()
    assert quotes_as_of([timed], 110) == (timed,)


def test_manifest_is_order_independent_and_honest_about_roi():
    match, quotes = normalize()
    first = dataset_manifest([match], quotes)
    second = dataset_manifest([match], reversed(quotes))
    assert first == second
    assert first['quote_count_by_market'] == {'1x2': 6, 'ou': 4, 'ah': 4, 'btts': 0}
    assert set(first['roi_status_by_market'].values()) == {'NOT_EVALUABLE_NO_TIMED_QUOTES'}
    assert first['coverage_exclusions']['quotes_missing_capture_time'] == 14


@pytest.mark.parametrize('changes', [
    {'FTHG': '', 'FTAG': '1'}, {'HomeTeam': 'X', 'AwayTeam': ' X '},
    {'AHh': '-0.3'}, {'B365H': 'NaN'}, {'Date': '2025-08-15'},
])
def test_bad_historical_rows_fail_closed(changes):
    with pytest.raises(ContractError):
        normalize({**ROW, **changes})


def test_missing_prices_remain_missing():
    match, quotes = normalize({**ROW, 'B365D': '', 'B365AHH': None, 'B365AHA': None})
    assert len(quotes) == 11
    assert match.result_status == 'final'


def test_csv_loader_and_cli_manifest(tmp_path, capsys):
    import csv
    from football_formula_engine.data_cli import main
    path = tmp_path / 'sample.csv'
    with path.open('w', newline='', encoding='utf-8') as target:
        writer = csv.DictWriter(target, fieldnames=list(ROW))
        writer.writeheader(); writer.writerow(ROW)
    matches, quotes = load_football_data_csv(path, competition_id='E0', season='2526', timezone_name='+01:00')
    assert len(matches) == 1 and len(quotes) == 14
    assert main([str(path), '--competition', 'E0', '--season', '2526', '--timezone', '+01:00']) == 0
    assert json.loads(capsys.readouterr().out)['roi_status_by_market']['btts'] == 'NOT_EVALUABLE_NO_TIMED_QUOTES'


def test_iana_timezone_without_database_fails_explicitly():
    # The local Windows interpreter currently has no tzdata. Environments that
    # provide it should parse successfully instead of being forced to fail.
    try:
        match, _ = normalize_football_data_row(ROW, competition_id='E0', season='2526',
                                               source_file='x.csv', source_row=2,
                                               timezone_name='Europe/London')
        assert match.kickoff_utc > 0
    except ContractError as exc:
        assert 'Timezone database unavailable' in str(exc)


def test_live_fixture_identity_and_as_of():
    row = {'I': 123, 'S': 1800003600, 'L': ' England. Premier League ', 'O1': ' Arsenal ', 'O2': 'Chelsea'}
    fixture = normalize_1xbit_fixture(row, observed_at_utc=1800000000)
    assert fixture.fixture_id == normalize_1xbit_fixture(row, observed_at_utc=1800000000).fixture_id
    assert fixture.competition_name == 'England. Premier League'
    assert fixture.kickoff_utc > fixture.observed_at_utc
    with pytest.raises(ContractError): normalize_1xbit_fixture(row, observed_at_utc=1800003600)


def test_forward_quote_freshness_and_timing():
    args = dict(fixture_id='f1', market='ah', side='home', line=-.75, decimal_odds=1.95,
                provider='provider', bookmaker='book', available_at_utc=100, captured_at_utc=110,
                decision_at_utc=120, fresh_for_seconds=15)
    quote = normalize_quote_snapshot(**args)
    assert quote.line_quarters == -3 and quote.freshness == 'fresh'
    assert normalize_quote_snapshot(**{**args, 'decision_at_utc': 126}).freshness == 'stale'
    with pytest.raises(ContractError): normalize_quote_snapshot(**{**args, 'captured_at_utc': 121})
    with pytest.raises(ContractError): normalize_quote_snapshot(**{**args, 'market': 'btts', 'side': 'yes'})
