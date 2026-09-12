import json
import math
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
from football_formula_engine.contracts import ContractError
from football_formula_engine.markets import asian_handicap, btts, match_odds, over_under, settle_score
from football_formula_engine.math_cli import main
from football_formula_engine.score_matrix import build_score_matrix, rho_bounds
from football_formula_engine.value import expected_value, fair_odds, proportional_no_vig


def assert_mass(payout):
    assert payout.mass == pytest.approx(1, abs=1e-12)


def test_score_matrix_adaptive_mass_and_tail():
    distribution = build_score_matrix(1.5, 1.2)
    assert sum(p for _, _, p in distribution.cells()) == pytest.approx(1, abs=1e-12)
    assert distribution.tail_mass_bound <= 1e-8
    assert distribution.max_goals > 1
    assert distribution.raw_mass < 1


def test_rho_validity_and_hard_limit():
    lower, upper = rho_bounds(1.5, 1.2)
    build_score_matrix(1.5, 1.2, lower)
    build_score_matrix(1.5, 1.2, upper)
    with pytest.raises(ContractError): build_score_matrix(1.5, 1.2, upper + 1e-6)
    with pytest.raises(ContractError): build_score_matrix(50, 50, hard_limit=2)


def test_dixon_coles_identity_for_over_25_but_not_btts():
    probabilities = []
    for rho in (-0.2, 0, 0.2):
        distribution = build_score_matrix(1.5, 1.2, rho)
        probabilities.append((over_under(distribution, 'over', 10).full_win, btts(distribution)['yes'].full_win))
    assert max(v[0] for v in probabilities) - min(v[0] for v in probabilities) < 1e-12
    assert len({round(v[1], 10) for v in probabilities}) == 3


def test_four_market_complements():
    distribution = build_score_matrix(1.7, 0.9, -0.05)
    one_x_two = match_odds(distribution)
    assert sum(v.full_win for v in one_x_two.values()) == pytest.approx(1)
    both = btts(distribution)
    assert both['yes'].full_win + both['no'].full_win == pytest.approx(1)
    for value in [*one_x_two.values(), *both.values(),
                  asian_handicap(distribution, 'home', -3), asian_handicap(distribution, 'away', 3),
                  over_under(distribution, 'over', 9), over_under(distribution, 'under', 9)]:
        assert_mass(value)


@pytest.mark.parametrize('market,side,line,score,expected', [
    ('ah', 'home', -3, (1, 0), 'half_win'),
    ('ah', 'home', -6, (3, 1), 'full_win'),
    ('ah', 'away', 3, (1, 0), 'half_loss'),
    ('ah', 'home', 0, (1, 1), 'push'),
    ('ou', 'over', 9, (1, 1), 'half_loss'),
    ('ou', 'under', 9, (1, 1), 'half_win'),
    ('ou', 'over', 10, (2, 1), 'full_win'),
    ('ou', 'under', 10, (1, 1), 'full_win'),
    ('1x2', 'draw', None, (1, 1), 'full_win'),
    ('btts', 'no', None, (2, 0), 'full_win'),
])
def test_golden_settlements(market, side, line, score, expected):
    payout = settle_score(market, side, line, *score)
    assert getattr(payout, expected) == 1
    assert_mass(payout)


def test_payout_aware_fair_odds_and_ev():
    from football_formula_engine.markets import PayoutProbabilities
    payout = PayoutProbabilities(.55, .10, .05, .05, .25)
    price = fair_odds(payout)
    assert price == pytest.approx(1.4583333333333333)
    assert expected_value(payout, price) == pytest.approx(0)
    assert expected_value(payout, 1.95) == pytest.approx(.295)
    assert expected_value(payout, fair_odds(payout, win_commission=.02), win_commission=.02) == pytest.approx(0)


def test_all_push_and_zero_win():
    from football_formula_engine.markets import PayoutProbabilities
    assert fair_odds(PayoutProbabilities(push=1)) is None
    assert expected_value(PayoutProbabilities(push=1), 2) == 0
    assert fair_odds(PayoutProbabilities(full_loss=1)) is None


@pytest.mark.parametrize('values', [(-.1, 0, 0, 0, 1.1), (.5, 0, 0, 0, .4), (math.nan, 0, 0, 0, 1)])
def test_invalid_payout_objects(values):
    from football_formula_engine.markets import PayoutProbabilities
    with pytest.raises(ContractError): PayoutProbabilities(*values)


def test_no_vig_is_scoped_and_sums_to_one():
    probabilities = proportional_no_vig([2.0, 3.5, 4.0])
    assert sum(probabilities) == pytest.approx(1)
    with pytest.raises(ContractError): proportional_no_vig([2])
    with pytest.raises(ContractError): proportional_no_vig([2, math.inf])


@pytest.mark.parametrize('market,side,line', [('ah', 'draw', 0), ('ou', 'home', 10), ('ou', 'over', -1)])
def test_invalid_market_contracts(market, side, line):
    distribution = build_score_matrix(1.2, 1.1)
    with pytest.raises(ContractError):
        (asian_handicap if market == 'ah' else over_under)(distribution, side, line)


def test_offline_math_cli_is_projection_only(capsys):
    assert main(['--lambda-home', '1.5', '--lambda-away', '1.2', '--rho', '-0.1', '--ou-line', '2.25', '--ah-line', '-0.75',
                 '--odds-json', '{"1x2.home":2.4,"ou.over":1.95}']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'projection_only' and result['official_enabled'] is False
    assert set(result) == {'status', 'official_enabled', 'matrix', '1x2', 'btts', 'ou', 'ah'}
    assert result['1x2']['home']['ev'] is not None and result['btts']['yes']['ev'] is None


@pytest.mark.parametrize('line', range(-12, 13))
def test_ah_opposite_side_contracts_are_payout_complements(line):
    distribution = build_score_matrix(1.45, 1.05, -.08)
    home, away = asian_handicap(distribution, 'home', line), asian_handicap(distribution, 'away', -line)
    assert home.full_win == pytest.approx(away.full_loss)
    assert home.half_win == pytest.approx(away.half_loss)
    assert home.push == pytest.approx(away.push)
    assert home.half_loss == pytest.approx(away.half_win)


@pytest.mark.parametrize('line', range(0, 17))
def test_ou_sides_are_payout_complements(line):
    distribution = build_score_matrix(1.45, 1.05, -.08)
    over, under = over_under(distribution, 'over', line), over_under(distribution, 'under', line)
    assert over.full_win == pytest.approx(under.full_loss)
    assert over.half_win == pytest.approx(under.half_loss)
    assert over.push == pytest.approx(under.push)
    assert over.half_loss == pytest.approx(under.half_win)
