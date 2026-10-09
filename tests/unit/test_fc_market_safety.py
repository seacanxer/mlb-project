from pathlib import Path
import runpy
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'betting-machine-fc'))
from football_formula_engine.market_safety import anchor_payout
from football_formula_engine.markets import PayoutProbabilities
from football_formula_engine.value import effective_win_loss
from football_formula_engine.catalog import select_markets


@pytest.mark.parametrize('payout', [
    PayoutProbabilities(full_win=.65, full_loss=.35),
    PayoutProbabilities(full_win=.5, half_win=.2, push=.1, full_loss=.2),
    PayoutProbabilities(full_win=.4, half_loss=.3, full_loss=.3),
])
def test_anchor_preserves_asian_payout_mass_and_targets_paid_probability(payout):
    adjusted, raw = anchor_payout(payout,.5,.5)
    w,l = effective_win_loss(adjusted)
    assert adjusted.mass == pytest.approx(1)
    assert adjusted.push == payout.push
    assert w/(w+l) == pytest.approx((raw+.5)/2)
    if payout.half_win:
        assert adjusted.full_win/adjusted.half_win == pytest.approx(payout.full_win/payout.half_win)
    if payout.half_loss:
        assert adjusted.full_loss/adjusted.half_loss == pytest.approx(payout.full_loss/payout.half_loss)


def test_low_odds_favorite_abstains_without_substituting_underdog():
    def offer(side,p,odds):
        return {'side':side,'probability':p,'odds':odds,'ev':.1,'conservative_ev':.08,
                'gate_reasons':[],'line_quarters':None,'market_probability':p}
    rows = [('1x2','Home',offer('home',.8,1.29)),
            ('1x2','Draw',offer('draw',.1,5)), ('1x2','Away',offer('away',.1,5))]
    forecasts,_ = select_markets(rows)
    assert forecasts == []
    rows[0][2]['odds'] = 1.30
    assert select_markets(rows)[0][0][2]['side']=='home'


def test_large_model_market_gap_is_not_a_value_candidate():
    scan = runpy.run_path(str(ROOT/'scripts/fc-scan-live.py'))
    payout = PayoutProbabilities(full_win=.8, full_loss=.2)
    assert scan['opp'](payout,1.95,.5,market='btts') is None
    priced = scan['opp'](payout,1.95,.5,market='btts',gated=False)
    assert 'MODEL_MARKET_DISAGREEMENT' in priced['gate_reasons']
    assert priced['probability'] == pytest.approx(.65)
    assert priced['raw_probability'] == .8
    assert select_markets([('btts','BTTS Yes',priced)])[0] == []
