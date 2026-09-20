import copy
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
from football_formula_engine.contracts import ContractError
from football_formula_engine.live_quotes import QuoteJournal, quote_rows
from football_formula_engine.outer_cli import fold_specs, validate_periods
from football_formula_engine.data import load_football_data_csv
from football_formula_engine.second_source import normalize_event
from football_formula_engine.score_matrix import build_score_matrix


def test_quote_history_timing_dedup_and_immutability(tmp_path):
    journal = QuoteJournal(tmp_path / 'quotes.db')
    info = {'match_id': '1', 'start_ts': 1000}
    mk = {'odds_ou': {2.5: {9: 2.0, 10: 1.9}}}
    first = journal.record(info, mk, {}, captured_at=800)
    assert len(first['quotes']) == 2
    assert first['source_updated_at'] is None
    assert journal.record(info, mk, {}, captured_at=800) == first
    journal.record(info, {'odds_ou': {2.5: {9: 1.8}}}, {}, captured_at=990)
    assert len(journal.as_of('1', 850)) == 1
    assert journal.as_of('1', 790) == []
    assert journal.as_of('1', 1000) == []
    closes = journal.closing('1', 1000, max_age_seconds=30)
    assert len(closes) == 1
    assert next(iter(closes.values()))['decimal_odds'] == 1.8
    with journal.connect() as db:
        assert db.execute('SELECT count(*) FROM observations').fetchone()[0] == 2
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('DELETE FROM observations')
    with pytest.raises(ContractError):
        journal.record(info, mk, {}, captured_at=1000)
    with pytest.raises(ContractError):
        journal.record(info, mk, {}, captured_at=800, source_updated_at=900)


def test_ah_preserves_signed_side_lines():
    rows = list(quote_rows({'odds_ah': {'home': [(-0.75, 2)], 'away': [(0.75, 1.9)]}}))
    assert rows == [('ah', 'home', -0.75, 2), ('ah', 'away', 0.75, 1.9)]


def test_research_decision_locks_first_price_and_rejects_invented_entry(tmp_path):
    journal = QuoteJournal(tmp_path / 'quotes.db')
    info = {'match_id': '1', 'start_ts': 1000}
    obs = journal.record(info, {'odds_ou': {2.5: {9: 2}}}, {}, captured_at=800)
    contract = {'market': 'ou', 'side': 'over', 'line_quarters': 10, 'decimal_odds': 2}
    first = journal.record_research_decision(obs['artifact_id'], contract, decision_at=810,
                                            policy_id='v1', model={'artifact_id': 'model'})
    second = journal.record_research_decision(obs['artifact_id'], contract, decision_at=820,
                                             policy_id='v1', model={'artifact_id': 'model-2'})
    assert first == second
    assert first['official_enabled'] is False
    with pytest.raises(ContractError):
        journal.record_research_decision(obs['artifact_id'], {**contract, 'decimal_odds': 5},
                                        decision_at=820, policy_id='v1', model={})
    with pytest.raises(ContractError):
        journal.record_research_decision(obs['artifact_id'], contract, decision_at=1000,
                                        policy_id='v1', model={})


def test_second_book_matching_excludes_changed_line_stale_and_same_book(tmp_path):
    journal = QuoteJournal(tmp_path / 'quotes.db')
    info = {'match_id': '1', 'start_ts': 1000}
    journal.record(info, {'odds_ou': {2.5: {9: 2}}}, {}, captured_at=800)
    journal.record(info, {'odds_ou': {3.5: {9: 2}}}, {}, captured_at=810,
                   provider='second', bookmaker='reference', source_updated_at=805)
    assert journal.compare_sources('1', 820)['pairs'] == []
    journal.record(info, {'odds_ou': {2.5: {9: 1.9}}}, {}, captured_at=810,
                   provider='second', bookmaker='reference', source_updated_at=805)
    result = journal.compare_sources('1', 820)
    assert len(result['pairs']) == 1
    assert result['pairs'][0]['source_freshness_verified'] is False
    assert journal.compare_sources('1', 820, max_skew_seconds=5)['pairs'] == []
    assert journal.compare_sources('1', 950, max_age_seconds=30)['pairs'] == []


def test_scan_persists_quotes_before_missing_model(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('fc_scan_integration', ROOT / 'scripts/fc-scan-live.py')
    scan = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scan)
    monkeypatch.setattr(scan, 'FC_DIR', str(tmp_path))
    monkeypatch.setenv('FC_QUOTES_DB', str(tmp_path / 'quotes.db'))
    monkeypatch.delenv('FC_SECOND_MAPPING_PATH', raising=False)
    monkeypatch.setattr(scan.time, 'time', lambda: 1000.0)
    monkeypatch.setattr(scan.time, 'sleep', lambda _: None)
    row = {'I': 1, 'S': 2000, 'O1': 'A', 'O2': 'B', 'L': 'England. Premier League',
           'E': [{'G': 17, 'T': 9, 'P': 2.5, 'C': 2.0}]}
    monkeypatch.setattr(scan.sc, 'list_matches_paginated', lambda **kwargs: [row])
    monkeypatch.setattr(scan.sc, 'get_match', lambda _: row)
    monkeypatch.setattr(scan, 'load_model', lambda *args: None)
    monkeypatch.setattr(scan, 'refresh_scores', lambda *args: {'status': 'unavailable'})
    monkeypatch.setattr(scan.odds_flashscore, 'crosscheck', lambda *args: {'status': 'unavailable'})
    assert scan.main() == 0
    journal = QuoteJournal(tmp_path / 'quotes.db')
    assert len(journal.as_of('1', 1000)[0]['quotes']) == 1
    assert json.loads((tmp_path / 'picks.json').read_text()) == []


def test_scan_prices_integer_ou_keys():
    spec = importlib.util.spec_from_file_location('fc_scan', ROOT / 'scripts/fc-scan-live.py')
    scan = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scan)
    offers = scan.price_fixture(build_score_matrix(1.5, 1.5, 0),
                                {'odds_ou': {2.5: {9: 3.0, 10: 3.0}}})
    assert any(market == 'ou' for market, _, _ in offers)


def event_fixture():
    event = {'id': 'abc', 'sport_key': 'soccer_epl', 'home_team': 'A', 'away_team': 'B',
             'commence_time': '2026-09-15T12:00:00Z', 'bookmakers': [{
                 'key': 'reference', 'last_update': '2026-09-15T10:00:00Z',
                 'markets': [{'key': 'spreads', 'outcomes': [
                     {'name': 'A', 'point': -0.75, 'price': 2.0},
                     {'name': 'B', 'point': 0.75, 'price': 1.9}]}]}]}
    from football_formula_engine.second_source import timestamp
    kickoff = timestamp(event['commence_time'])
    mapping = {'event_id': 'abc', 'sport_key': 'soccer_epl', 'source_home': 'A', 'source_away': 'B',
               'fixture': {'match_id': '1', 'start_ts': kickoff}}
    return event, mapping, kickoff - 300


@pytest.mark.parametrize('field,value', [('id', 'wrong'), ('home_team', 'B'),
                                       ('sport_key', 'other'), ('commence_time', '2026-09-16T12:00:00Z')])
def test_second_source_rejects_wrong_mapping(field, value):
    event, mapping, now = event_fixture()
    event[field] = value
    with pytest.raises(ContractError):
        normalize_event(event, mapping, 'reference', now)


def test_second_source_signed_lines_and_timestamp():
    event, mapping, now = event_fixture()
    markets, updated = normalize_event(event, mapping, 'reference', now)[0]
    assert markets['odds_ah']['home'] == [(-0.75, 2)]
    assert markets['odds_ah']['away'] == [(0.75, 1.9)]
    assert updated < now
    with pytest.raises(ContractError):
        normalize_event(event, mapping, 'missing', now)


def test_two_real_outer_periods_are_disjoint_and_chronological():
    base = json.loads((ROOT / 'betting-machine-fc/football_formula_engine/evaluation_spec.json').read_text())
    matches = []
    for source in base['dataset']:
        rows, _ = load_football_data_csv(ROOT / source['path'], competition_id='E0',
                                       season=source['season'], timezone_name=base['timezone'])
        matches.extend(rows)
    specs = fold_specs(base)
    validate_periods(matches, specs)
    with pytest.raises(ContractError):
        validate_periods(matches, [specs[0], copy.deepcopy(specs[0])])
