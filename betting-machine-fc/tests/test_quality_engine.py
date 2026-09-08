import math
import time

import pytest

from model import score_matrix, total_ev, ah_ev, ah_ev_away
from market_quality import outcome_distribution, payout_metrics, recommendation_block
from match_prediction import build_full_matrix, matrix_over_under, compute_prediction_card


@pytest.mark.parametrize('market,side,line', [('ou','over',2), ('ou','under',2.25), ('ou','over',2.75), ('ah','home',-.75), ('ah','away',.25)])
def test_exact_outcome_probabilities_reproduce_payout_engine(market, side, line):
    metrics = payout_metrics(market, side, line, 1.95, 1.5, 1.2)
    assert sum(metrics[k] for k in ('full_win','half_win','push','half_loss','full_loss')) == pytest.approx(1)
    expected = total_ev(line, side, 1.95, 1.5, 1.2) if market == 'ou' else (ah_ev if side == 'home' else ah_ev_away)(line,1.95,1.5,1.2)
    assert metrics['ev'] == pytest.approx(expected)
    assert metrics['win_fraction']*(metrics['fair_odds']-1)-metrics['loss_fraction'] == pytest.approx(0)


def test_integer_push_and_quarter_half_loss_are_not_under_wins():
    matrix = [[0,0,1], [0,0,0], [0,0,0]]
    assert matrix_over_under(matrix, 2) == (0,0)
    assert matrix_over_under(matrix, 2.25) == (0,.5)
    assert outcome_distribution({(0,2): 1}, 'ou', 'over', 2.25)['half_loss'] == 1


def test_every_menu_uses_the_same_normalized_grid():
    card = build_full_matrix(3.8, 2.1)
    matrix, _ = score_matrix(3.8, 2.1)
    assert len(card) == 11
    for (h,a), value in matrix.items():
        assert card[h][a] == value
    assert sum(map(sum, card)) == pytest.approx(1)


@pytest.mark.parametrize('lh,la,rho', [(float('nan'),1,-.13),(0,1,-.13),(5,5,-.3)])
def test_invalid_distribution_is_rejected(lh,la,rho):
    with pytest.raises(ValueError):
        score_matrix(lh,la,rho)


def test_prediction_no_fabricated_inputs_or_squad():
    with pytest.raises(ValueError):
        compute_prediction_card({})
    match = {'lambdas': {'home': 1.5, 'away': 1.2}, 'info': {'home':'A','away':'B'}, 'model': {'coverage_status':'shadow'}}
    with pytest.raises(ValueError):
        compute_prediction_card(match, beta_squad=.2)
    card = compute_prediction_card(match)
    assert card['decision'] == 'NO BET'
    assert not card['qualified_picks']
    assert card['recommended']['ou'] is None
    assert card['model_lean']['ou']


def test_intel_cannot_promote_shadow_with_elo(monkeypatch):
    import intel
    monkeypatch.setattr(intel.elo_rating, 'elo_hybrid', lambda *a: (2,1,'market+elo'))
    market = {'home':'A','away':'B','league':'USA. MLS', 'start_ts':time.time()+3600,
              'odds_1x2':{1:2.2,2:3.4,3:3.1}, 'odds_ou':{2.5:{9:1.95,10:1.95}}}
    result = intel.analyze_intel(market)
    assert result['coverage'] == 'shadow'
    assert result['recommendation'] is None


def test_rating_intercepts_reproduce_observed_home_and_away_totals():
    from strength_rating import mle_rating
    from model import strength_lam
    rows = [{'date':'2025-01-01','home':h,'away':a,'fthg':2,'ftag':1} for h in 'ABCD' for a in 'ABCD' if h!=a]
    teams, avg, adv = mle_rating(rows, time_decay_per_day=0)
    predictions = [strength_lam(teams[r['home']]['att'],teams[r['away']]['def'],teams[r['away']]['att'],teams[r['home']]['def'],avg,adv) for r in rows]
    assert sum(h for h,a in predictions) == pytest.approx(24, abs=.01)
    assert sum(a for h,a in predictions) == pytest.approx(12, abs=.01)


def test_lock_is_immutable_and_carries_formula_audit(tmp_path,monkeypatch):
    import db
    monkeypatch.setattr(db,'DB_PATH',str(tmp_path/'locks.db'))
    db.init_db()
    pick = {'match':'A vs B','match_id':'1','start_ts':time.time()+3600,'market':'ou','pick':'Over 2.5','odds':1.95,'ev':.1,'formula_version':'v-test','policy_version':'quality-v1'}
    lock_id, created = db.insert_bet(pick)
    assert created
    db.insert_bet(dict(pick,pick='Under 2.5',odds=2.2,ev=.2))
    with db._connect() as conn:
        row = conn.execute('SELECT pick,odds FROM bets WHERE id=?',(lock_id,)).fetchone()
        assert (row['pick'],row['odds']) == ('Over 2.5',1.95)
        assert conn.execute('SELECT policy_version FROM bet_audit WHERE bet_id=?',(lock_id,)).fetchone()[0] == 'quality-v1'


def test_prediction_api_reports_missing_inputs_as_422(monkeypatch):
    import server
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server, 'load_detailed_matches', lambda: [{'info': {'match_id':'missing'}}])
    client = TestClient(server.app)
    assert client.get('/api/prediction/missing').status_code == 422
    assert client.post('/api/prediction/compute', json={'fixture_key':'missing'}).status_code == 422


def test_intel_explicit_filter_does_not_restore_legacy_recommendations(monkeypatch):
    import server, intel
    from fastapi.testclient import TestClient
    monkeypatch.setattr(intel, 'load_board', lambda: {'board':[{
        'start_ts':time.time()+3600, 'coverage':'full', 'decision':'WATCH',
        'recommendation':{'market':'ou', 'ev':.1}}]})
    client = TestClient(server.app)
    assert client.get('/api/intel?decision=WATCH').json()['board'] == []
    item = client.get('/api/intel?decision=NO%20BET').json()['board'][0]
    assert item['recommendation'] is None
