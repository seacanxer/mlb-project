"""P0 evidence only: no production pipeline or ledger changes."""
from datetime import date
import math
from pathlib import Path
import runpy
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
from football_formula_engine.reliability import reliability_report
from football_formula_engine.score_matrix import build_score_matrix
from football_formula_engine.markets import asian_handicap, over_under, match_odds
from football_formula_engine.value import expected_value, fair_odds
import scores_flashscore
import scraper_1xbit


def test_reliability_includes_push_as_nonwin_and_roi_as_actual_return():
    rows = [dict(probability=.75, outcome=1, profit=.8, result_verified=True),
            dict(probability=.25, outcome=0, profit=0, result_verified=True)]
    result = reliability_report(rows)
    assert result['brier'] == .0625
    assert result['log_loss'] == pytest.approx(-math.log(.75))
    assert result['roi_pct'] == 40
    assert result['pushes'] == 1


def test_empty_invalid_and_unverified_are_not_zero_performance():
    result = reliability_report([dict(probability=float('nan'), outcome=1, profit=1, result_verified=True),
                                 dict(probability=.5, outcome=1, profit=1, result_verified=False)])
    assert result['n'] == 0 and result['excluded'] == 2
    assert result['brier'] is None and result['roi_pct'] is None


def test_bucket_boundaries_and_log_loss_extremes():
    result = reliability_report([dict(probability=p, outcome=y, profit=2*y-1, result_verified=True)
                                 for p, y in [(0, 1), (.5, 1), (1, 0)]])
    assert [b['lower'] for b in result['buckets']] == [0, .5, .9]
    assert math.isfinite(result['log_loss'])


def test_matrix_orientation_and_fair_price_zero_ev_for_quarters():
    dist = build_score_matrix(2.1, .8, -.03)
    reverse = build_score_matrix(.8, 2.1, -.03)
    assert match_odds(dist)['home'].full_win > match_odds(dist)['away'].full_win
    assert match_odds(dist)['home'].full_win == pytest.approx(match_odds(reverse)['away'].full_win)
    for side in ('home', 'away'):
        for q in range(-12, 13):
            payout = asian_handicap(dist, side, q)
            assert expected_value(payout, fair_odds(payout)) == pytest.approx(0, abs=1e-12)
    for side in ('over', 'under'):
        for q in range(2, 23):
            payout = over_under(dist, side, q)
            assert expected_value(payout, fair_odds(payout)) == pytest.approx(0, abs=1e-12)


def test_p0_reproduces_token_matcher_false_positive():
    row = dict(home='Manchester United', away='West Brom', home_goals=3,
               away_goals=0, date_key='2026-09-25')
    lookup = scores_flashscore.build_lookup({('manchester united', 'west brom'): row})
    found = scores_flashscore.find_result('Manchester City', 'West Ham', lookup, date(2026, 9, 25))
    # Evidence of the CURRENT defect; P1 must replace this behavior.
    assert found is None


def test_p0_reproduces_legacy_1x2_label_failure():
    settle = runpy.run_path(str(ROOT / 'scripts/fc-settle-live.py'))['settle_bet']
    assert settle('1x2', 'Home (Example Home)', 2.07, 1, 0) == (1, 1.07)


def test_provider_adapter_preserves_declared_sides_and_quarter_lines():
    raw = {'I': 1, 'O1': 'Home FC', 'O2': 'Away FC', 'E': [
        {'G': 2, 'T': 7, 'P': -.25, 'C': 1.9},
        {'G': 2, 'T': 8, 'P': .25, 'C': 2.0},
        {'G': 17, 'T': 9, 'P': 2.25, 'C': 1.8},
        {'G': 17, 'T': 10, 'P': 2.25, 'C': 2.1}]}
    parsed = scraper_1xbit.extract_markets(raw)
    assert (parsed['home'], parsed['away']) == ('Home FC', 'Away FC')
    assert parsed['odds_ah'] == {'home': [(-.25, 1.9)], 'away': [(.25, 2.0)]}
    assert parsed['odds_ou'][2.25] == {9: 1.8, 10: 2.1}


def test_provider_adapter_ingests_split_quarter_groups():
    raw = {'I': 2, 'O1': 'Spain', 'O2': 'Croatia', 'E': [
        {'G': 99, 'T': 3827, 'P': 3.25, 'C': 1.986},
        {'G': 99, 'T': 3828, 'P': 3.25, 'C': 1.954},
        {'G': 2854, 'T': 3829, 'P': -1.75, 'C': 1.782},
        {'G': 2854, 'T': 3830, 'P': 1.75, 'C': 2.202}]}
    parsed = scraper_1xbit.extract_markets(raw)
    assert parsed['odds_ou'][3.25] == {9: 1.986, 10: 1.954}
    assert parsed['odds_ah'] == {'home': [(-1.75, 1.782)],
                                 'away': [(1.75, 2.202)]}
