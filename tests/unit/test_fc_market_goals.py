from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))

from football_formula_engine.market_goals import infer_market_goals, blend_goal_projection


def spain_croatia_market():
    return {
        'odds_1x2': {1: 1.25, 2: 7.31, 3: 12.7},
        'odds_ou': {
            2.5: {9: 1.43, 10: 2.59}, 3.0: {9: 1.666, 10: 2.12},
            3.25: {9: 1.986, 10: 1.954}, 3.5: {9: 2.211, 10: 1.776},
            4.0: {9: 2.82, 10: 1.39}}}


def test_market_anchor_recovers_high_total_and_strong_home_favorite():
    result = infer_market_goals(spain_croatia_market())
    assert result['total_lines'] == 5
    assert 3.3 < result['total'] < 3.9
    assert result['home'] > 2.5
    assert result['away'] < 1.1


def test_market_blend_tempers_extreme_historical_projection():
    market = infer_market_goals(spain_croatia_market())
    home, away = blend_goal_projection(1.8, 1.2, market)
    assert 1.8 < home < market['home']
    assert market['away'] < away < 1.2


def test_spain_croatia_pre_match_reference_total_is_comparable_not_hardcoded():
    market = infer_market_goals(spain_croatia_market())
    # Historical inputs were produced at a cutoff before kickoff. The blend
    # should reproduce the peer's 3.42 total range without using the 4-1 result.
    home, away = blend_goal_projection(2.011798, 1.232502, market)
    assert home + away == pytest.approx(3.44848, abs=.01)
    assert home > away


def test_anchor_requires_complete_independent_market_shapes():
    assert infer_market_goals({'odds_1x2': {1: 2, 2: 3}}) is None
    with pytest.raises(ValueError):
        blend_goal_projection(1, 1, {'home': 1, 'away': 1}, 1.1)
