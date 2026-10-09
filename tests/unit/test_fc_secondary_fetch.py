from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'betting-machine-fc'))
import scraper_1xbit as sc


def test_grouped_parser_handles_nested_string_codes_and_rejects_invalid_prices():
    ou, ah = sc._parse_ou_ah([
        {'G': '17', 'E': [[{'T': '9', 'C': '1.95', 'P': '9.75'}, {'T': '10', 'C': 1.9, 'P': 9.75}]]},
        {'G': 2, 'E': [{'T': 7, 'C': 1.9, 'P': -2.25}, {'T': 8, 'C': float('inf'), 'P': 2.25}]},
        {'G': 17, 'T': 9, 'C': 1.9, 'P': float('nan')},
        {'G': 17, 'T': 9, 'C': 1.9, 'P': 9.73},
    ])
    assert ou == {9.75: {9: 1.95, 10: 1.9}}
    assert ah == {'home': [(-2.25, 1.9)], 'away': []}


def test_secondary_fetch_retries_and_keeps_only_verified_full_time_subgames(monkeypatch):
    calls = []
    def grouped(mid, country=169):
        calls.append(mid)
        if len(calls) == 1:
            raise TimeoutError('temporary')
        if mid == 100:
            return {'I': 100, 'SG': [
                {'I': 200, 'TI': '2', 'MG': 100},
                {'I': 201, 'TI': 2, 'P': 1, 'MG': 100},
                {'I': 202, 'TI': 10, 'MG': 999}]}
        return {'I': 200, 'MG': 100, 'GE': [{'G': 17, 'E': [
            {'T': 9, 'P': 9.75, 'C': 1.9}, {'T': 10, 'P': 9.75, 'C': 1.9}]}]}
    monkeypatch.setattr(sc, 'get_match_grouped', grouped)
    result = sc.extract_secondary_markets(100)
    assert calls == [100, 100, 200]
    assert result['secondary_subgame_ids'] == {'corners': 200}
    assert result['odds_corners_ou'][9.75][9] == 1.9
    assert result['secondary_fetch']['markets']['corners']['captured_at'] > 0


@pytest.mark.parametrize('wrong_parent', [False, True])
def test_secondary_fetch_rejects_mismatched_fixture_and_exposes_failure(monkeypatch, wrong_parent):
    def grouped(mid, country=169):
        if mid == 100 and wrong_parent:
            return {'I': 100, 'SG': [{'I': 200, 'TI': 2, 'MG': 100}]}
        return {'I': 999 if not wrong_parent else 200, 'MG': 999,
                'E': [{'G': 17, 'T': 9, 'P': 9.5, 'C': 1.9}]}
    monkeypatch.setattr(sc, 'get_match_grouped', grouped)
    result = sc.extract_secondary_markets(100)
    assert not any(result[k] for k in sc.SECONDARY_KEYS)
    assert result['secondary_fetch']['status'] == 'unavailable'
    if wrong_parent:
        assert result['secondary_fetch']['markets']['corners']['status'] == 'fetch_failed'
    else:
        assert 'ID_MISMATCH' in result['secondary_fetch']['error']
