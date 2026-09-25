import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from football_formula_engine.catalog import select_markets
from football_formula_engine.score_matrix import build_score_matrix
from football_formula_engine.live_training import current_season, refresh_scores

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('scan_catalog_tests', ROOT / 'scripts/fc-scan-live.py')
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)


def test_supported_competitions_and_daily_scan_window():
    assert scan.WINDOW_HOURS == 24
    assert scan.LEAGUE_BY_NAME['england. national league'] == 'EC'
    assert scan.LEAGUE_BY_NAME['belgium. jupiler league'] == 'B1'
    assert scan.model_code('UEFA Nations League') == 'INT_MEN'
    assert scan.model_code('UEFA Nations League. Team vs Player') is None


def test_national_forecast_is_held_on_large_market_gap():
    rows = [('1x2', side, {'probability': p, 'market_probability': q})
            for side, p, q in [('Home', .70, .40), ('Draw', .20, .30), ('Away', .10, .30)]]
    assert scan.national_market_reason(rows) == 'MODEL_MARKET_DISAGREEMENT'
    assert scan.national_market_reason(rows[:2]) == 'MARKET_BENCHMARK_UNAVAILABLE'
    assert scan.national_market_reason([('1x2', side, {'probability': .3, 'market_probability': .3})
                                        for side in ('Home', 'Draw', 'Away')]) is None


def markets():
    return {'odds_1x2': {1: 2.0, 2: 3.5, 3: 3.5},
            'odds_btts': {'yes': 1.95, 'no': 1.95},
            'odds_ou': {2.5: {9: 1.95, 10: 1.95}},
            'odds_ah': {'home': [(-0.5, 1.95)], 'away': [(0.5, 1.95)]}}


@pytest.mark.parametrize('home,away,expected', [(2.4, 1.8, 'over'), (0.7, 0.6, 'under')])
def test_total_direction_responds_to_actual_goal_model(home, away, expected):
    forecasts, _ = select_markets(scan.price_fixture(build_score_matrix(home, away, 0), markets(), gated=False))
    assert next(row[2]['side'] for row in forecasts if row[0] == 'ou') == expected


@pytest.mark.parametrize('home,away,expected', [(2.7, 0.5, 'home'), (0.7, 1.8, 'away')])
def test_handicap_selects_minus_or_plus_without_sign_quota(home, away, expected):
    forecasts, _ = select_markets(scan.price_fixture(build_score_matrix(home, away, 0), markets(), gated=False))
    ah = next(row[2] for row in forecasts if row[0] == 'ah')
    assert ah['side'] == expected
    assert ah['line_quarters'] == (-2 if expected == 'home' else 2)


def test_away_favorite_can_give_handicap_and_home_can_receive():
    mk = {'odds_ah': {'home': [(0.5, 1.95)], 'away': [(-0.5, 1.95)]}}
    forecasts, _ = select_markets(scan.price_fixture(build_score_matrix(0.5, 2.7, 0), mk, gated=False))
    assert forecasts[0][2]['side'] == 'away'
    assert forecasts[0][2]['line_quarters'] == -2


def test_forecasts_remain_visible_below_value_gate():
    mk = {'odds_ou': {2.5: {9: 1.1, 10: 1.1}}, 'odds_btts': {'yes': 1.1, 'no': 1.1}}
    offers = scan.price_fixture(build_score_matrix(1.35, 1.35, 0), mk, gated=False)
    forecasts, picks = select_markets(offers)
    assert len(forecasts) == 2
    assert picks == []
    assert all('ODDS_OUTSIDE_VALUE_RANGE' in row[2]['gate_reasons'] for row in forecasts)


def test_one_value_option_per_market_replaces_one_per_fixture():
    forecasts, picks = select_markets(scan.price_fixture(build_score_matrix(2.7, 0.5, 0), markets(), gated=False))
    assert len(forecasts) == 4
    assert len(picks) >= 2
    assert len({row[0] for row in picks}) == len(picks)


def test_extreme_total_line_does_not_win_display_on_high_probability():
    mk = {'odds_ou': {2.5: {9: 1.95, 10: 1.95}, 8.5: {9: 30.0, 10: 1.01}}}
    forecasts, _ = select_markets(scan.price_fixture(build_score_matrix(1.6, 1.4, 0), mk, gated=False))
    assert forecasts[0][2]['line_quarters'] == 10


def test_quarter_line_probability_and_ev_keep_half_outcomes():
    mk = {'odds_ou': {2.25: {9: 1.95, 10: 1.95}}}
    offers = scan.price_fixture(build_score_matrix(1.2, 1.0, 0), mk, gated=False)
    for _, _, offer in offers:
        p = offer['payout']
        assert offer['probability'] == pytest.approx(p['full_win'] + p['half_win'])
        assert offer['ev'] == pytest.approx((offer['odds'] - 1) * (p['full_win'] + .5 * p['half_win']) - p['full_loss'] - .5 * p['half_loss'])


@pytest.mark.parametrize('bad', [None, 'bad', 0, float('nan'), float('inf')])
def test_bad_or_incomplete_market_never_gets_priced(bad):
    assert scan.price_fixture(build_score_matrix(1.5, 1.3, 0), {'odds_ou': {2.5: {9: bad, 10: 1.95}}}, gated=False) == []


def test_failed_download_keeps_existing_scores(tmp_path, monkeypatch):
    now = 1789900000
    assert current_season(now) == '2627'
    target = tmp_path / 'E0_2627_live_scores.csv'
    target.write_text('existing data')
    def broken(*args, **kwargs):
        raise OSError('offline')
    monkeypatch.setattr('urllib.request.urlopen', broken)
    assert refresh_scores('E0', tmp_path, now, max_age=0)['status'] == 'unavailable'
    assert target.read_text() == 'existing data'


def test_team_matching_does_not_choose_ambiguous_short_name_or_reserve():
    assert scan.match_team('United', {'Man United', 'Newcastle'}) is None
    assert scan.match_team('Arsenal U21', {'Arsenal'}) is None
    assert scan.match_team('Man City', {'Man City', 'Man United'}) == 'Man City'


def test_scottish_division_codes_match_csv_and_known_club_names():
    assert scan.model_code('Scotland. Championship') == 'SC1'
    assert scan.model_code('Scotland. League One') == 'SC2'
    assert scan.model_code('Scotland. League Two') == 'SC3'
    teams = scan.csv_teams('SC1')
    assert scan.match_team('Arbroath', teams) == 'Arbroath'
    assert scan.match_team("Queen's Park", teams) == 'Queens Park'
    assert scan.match_team('Inverness', teams) == 'Inverness C'
    assert scan.match_team('Greenock Morton', teams) == 'Morton'


def test_scan_writes_four_market_catalog_and_clears_old_missing_team_picks(tmp_path, monkeypatch):
    monkeypatch.setattr(scan, 'FC_DIR', str(tmp_path))
    monkeypatch.setenv('FC_QUOTES_DB', str(tmp_path / 'quotes.db'))
    monkeypatch.delenv('FC_SECOND_MAPPING_PATH', raising=False)
    monkeypatch.setattr(scan.time, 'time', lambda: 1789900000.0)
    monkeypatch.setattr(scan.time, 'sleep', lambda _: None)
    monkeypatch.setattr(scan, 'refresh_scores', lambda *args: {'status': 'cached'})
    monkeypatch.setattr(scan, 'MODEL_DATA_INFO', {})
    base = {'S': 1789903600, 'O1': 'Home', 'O2': 'Away', 'L': 'England. Premier League'}
    rows = [dict(base, I=1), dict(base, I=2, O1='Unknown')]
    (tmp_path / 'matches_detailed.json').write_text(json.dumps([{'info': {'match_id': '2', 'start_ts': base['S']}, 'picks': [{'pick': 'old'}]}]))
    monkeypatch.setattr(scan.sc, 'list_matches_paginated', lambda **kwargs: rows)
    monkeypatch.setattr(scan.sc, 'get_match', lambda mid: next(row for row in rows if str(row['I']) == mid))
    monkeypatch.setattr(scan.sc, 'extract_markets', lambda _: markets())
    monkeypatch.setattr(scan.odds_flashscore, 'crosscheck', lambda *args: {'status': 'unavailable'})
    monkeypatch.setattr(scan, 'load_model', lambda *args: {'parameters': {'season_effects': {'2627': {}}}, 'training': {'cutoff_utc': 1789890000}})
    monkeypatch.setattr(scan, 'csv_teams', lambda _: {'Home', 'Away'})
    monkeypatch.setattr(scan, 'project_fixture', lambda *args, **kwargs: SimpleNamespace(distribution=build_score_matrix(2.7, .5, 0), reason_codes=(), lambda_home=2.7, lambda_away=.5))
    monkeypatch.setattr(scan.QuoteJournal, 'record_research_decision', lambda *args, **kwargs: {'artifact_id': 'test-research'})
    assert scan.main() == 0
    matches = json.loads((tmp_path / 'matches_detailed.json').read_text())
    assert len(matches[0]['projections']) == 4
    assert len(matches[0]['qualified_picks']) >= 2
    assert all(not p['official_eligible'] for p in matches[0]['market_options'])
    assert matches[1]['picks'] == []
    assert matches[1]['analysis']['reason_codes'] == ['TEAM_COVERAGE_MISSING']
    assert not (tmp_path / 'bets.db').exists()
