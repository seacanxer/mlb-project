"""Regression probes for the concrete phase-1 defects and new quant boundary."""
import copy
from io import BytesIO
import json
from pathlib import Path
import runpy
import sqlite3
import sys
from urllib.error import HTTPError

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'betting-machine-fc'))
from football_formula_engine.contracts import ContractError
from football_formula_engine.live_quotes import QuoteJournal
from football_formula_engine.markets import PayoutProbabilities
from football_formula_engine.parlays import evaluate_parlay, build_value_parlays, score_joint_returns, resolve_choices
from football_formula_engine.quant import fractional_kelly, quant_metrics
from football_formula_engine.reference_odds import capture
from football_formula_engine.score_matrix import build_score_matrix
from football_formula_engine.sharp_reference import reference_snapshot

NOW = 1_900_000_000


def evidence():
    return {'observation_id': 'observed', 'captured_at': NOW-10, 'source_updated_at': NOW-12,
            'freshness_status': 'verified', 'bookmaker': 'pinnacle', 'decimal_odds': 1.7}


def leg(event='event-1', payout=None, odds=1.9, market='1x2', side='home', q=None):
    payout = payout or PayoutProbabilities(full_win=.6, full_loss=.4)
    w, l = payout.full_win+.5*payout.half_win, payout.full_loss+.5*payout.half_loss
    quant = quant_metrics(payout, odds, market_no_vig=.5, model_probability=.58,
        reference_probability=w/(w+l), reference_evidence=evidence(), decision_source='sharp')
    return {'event_key': event, 'start_ts': NOW+7200, 'quote_captured_at': NOW-10,
            'market': market, 'side': side, 'line_quarters': q, 'odds': odds,
            'payout': payout.__dict__, 'quant': quant}


@pytest.mark.parametrize('captured,updated,expected', [
    (NOW-5, NOW-3600, 'REFERENCE_SOURCE_EXPIRED'),
    (NOW-1000, NOW-1001, 'REFERENCE_CAPTURE_EXPIRED'),
    (NOW-5, None, 'REFERENCE_SOURCE_TIME_UNKNOWN'),
    (NOW+1, NOW, 'REFERENCE_CAPTURE_EXPIRED'),
    (NOW-5, NOW-4, 'REFERENCE_SOURCE_EXPIRED'),
    (NOW-400, NOW-402, 'REFERENCE_CAPTURE_SKEW'),
])
def test_reference_rejects_stale_unknown_future_and_skew(captured, updated, expected):
    obs = {'bookmaker':'pinnacle', 'captured_at':captured, 'source_updated_at':updated,
           'artifact_id':'a', 'quotes':[{'market':'btts','side':s,'line_quarters':None,'decimal_odds':1.9}
                                     for s in ('yes','no')]}
    result = reference_snapshot([obs], 'pinnacle', NOW, primary_captured_at=NOW-5)
    assert result['fair'] == {}
    assert expected in result['reason_codes']


def test_new_incomplete_market_never_borrows_old_opposite_side(tmp_path):
    journal = QuoteJournal(tmp_path/'q.db')
    fixture = {'match_id':'one','start_ts':NOW+3600}
    old = journal.record(fixture, {'odds_ou':{2.75:{9:1.9,10:1.9}}}, {},
                         captured_at=NOW-20, source_updated_at=NOW-22, bookmaker='pinnacle')
    new = journal.record(fixture, {'odds_ou':{2.75:{9:2.0}}}, {},
                         captured_at=NOW-10, source_updated_at=NOW-12, bookmaker='pinnacle')
    result = reference_snapshot([old,new], 'pinnacle', NOW)
    assert result['quotes'] == {}
    assert result['reason_codes'] == ['REFERENCE_COMPLETE_MARKET_UNAVAILABLE']


def test_fresh_quarter_reference_keeps_exact_handicap_side(tmp_path):
    journal = QuoteJournal(tmp_path/'q.db')
    obs = journal.record({'match_id':'one','start_ts':NOW+3600},
        {'odds_ah':{'home':[(-.75,1.9)],'away':[(.75,1.9)]}}, {},
        captured_at=NOW-10, source_updated_at=NOW-12, bookmaker='pinnacle')
    result = reference_snapshot([obs], 'pinnacle', NOW)
    assert result['fair'] == {('ah','home',-3):.5,('ah','away',3):.5}
    assert result['quotes'][('ah','away',3)]['observation_id'] == obs['artifact_id']


def test_research_contract_identity_and_legacy_data_are_preserved(tmp_path):
    journal = QuoteJournal(tmp_path/'q.db')
    with journal.connect() as db:
        db.execute('INSERT INTO research_decisions VALUES (?,?,?)', ('old','policy','{}'))
    obs = journal.record({'match_id':'one','start_ts':NOW+3600},
        {'odds_1x2':{1:2.0},'odds_ou':{2.5:{9:2.0}}}, {}, captured_at=NOW-10)
    one = {'market':'1x2','side':'home','line_quarters':None,'decimal_odds':2.0}
    two = {'market':'ou','side':'over','line_quarters':10,'decimal_odds':2.0}
    def record(contract, version='v1'):
        return journal.record_research_decision(obs['artifact_id'], contract, decision_at=NOW,
                                               policy_id='policy', model={'formula_version':version})
    first, second = record(one), record(two)
    assert second['contract'] == two and first['artifact_id'] != second['artifact_id']
    assert record(two) == second
    assert record(two, 'v2')['artifact_id'] != second['artifact_id']
    with pytest.raises(ContractError):
        record({**one, 'period': 'first_half'})
    with journal.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM research_decisions').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM research_decisions_v2').fetchone()[0] == 3
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE research_decisions_v2 SET payload='{}'")


@pytest.mark.parametrize('code,reason', [(401,'AUTHENTICATION_FAILED'),(403,'ACCESS_DENIED'),
    (429,'RATE_LIMIT_OR_QUOTA'),(503,'PROVIDER_UNAVAILABLE')])
def test_http_diagnostics_never_leak_api_key(code, reason, tmp_path):
    def opener(*args, **kwargs):
        raise HTTPError('https://example/?apiKey=SECRET_VALUE', code, 'SECRET_VALUE', {}, BytesIO(b'SECRET_VALUE'))
    result = capture({'sport':[{'match_id':'1'}]}, QuoteJournal(tmp_path/'q.db'),
                     api_key='SECRET_VALUE', bookmaker='pinnacle', opener=opener)
    assert result['sport']['http_status'] == code
    assert result['sport']['failure_reason'] == reason
    assert 'SECRET_VALUE' not in json.dumps(result)


def test_binary_kelly_matches_closed_form_and_cap():
    payout = PayoutProbabilities(full_win=.52, full_loss=.48)
    result = fractional_kelly(payout, 2, bankroll_units=100)
    assert result['full_fraction'] == pytest.approx(.04)
    assert result['recommended_fraction'] == pytest.approx(.01)
    assert result['recommended_units'] == pytest.approx(1.0)
    assert fractional_kelly(PayoutProbabilities(full_win=.8, full_loss=.2),2)['recommended_fraction'] == .02


def test_quarter_kelly_optimizes_all_payout_outcomes():
    payout = PayoutProbabilities(full_win=.4, half_win=.2, push=.1, half_loss=.1, full_loss=.2)
    result = fractional_kelly(payout,2)
    f = result['full_fraction']
    derivative = .4/(1+f)+.2*.5/(1+.5*f)-.1*.5/(1-.5*f)-.2/(1-f)
    assert derivative == pytest.approx(0, abs=1e-12)
    assert f != pytest.approx(.6-.4)  # binary shortcut with P(positive payout) is wrong
    assert fractional_kelly(PayoutProbabilities(push=1),2)['recommended_fraction'] == 0
    assert fractional_kelly(PayoutProbabilities(full_win=.4,full_loss=.6),2)['recommended_fraction'] == 0


@pytest.mark.parametrize('kwargs',[{'cap':.04},{'fraction':0},{'bankroll_units':float('nan')},{'bankroll_units':-1}])
def test_invalid_staking_config_is_rejected(kwargs):
    with pytest.raises(ContractError):
        fractional_kelly(PayoutProbabilities(full_win=.6, full_loss=.4),2,**kwargs)


def test_quant_separates_event_and_price_probability_and_abstains_without_proof():
    p = PayoutProbabilities(full_win=.4, half_win=.2, push=.1, half_loss=.1, full_loss=.2)
    result = quant_metrics(p,2, market_no_vig=.5, model_probability=.6)
    assert result['positive_payout_probability'] == pytest.approx(.6)
    assert result['decision_price_probability'] == pytest.approx(2/3)
    assert result['ev'] == pytest.approx(.25)
    assert result['status'] == 'forecast'
    assert result['kelly']['recommended_fraction'] == 0
    assert result['kelly']['recommended_units'] is None


def test_independent_parlay_is_compounded_from_payouts_and_preview_only():
    result = evaluate_parlay([leg(),leg('event-2')], now=NOW)
    assert result['eligible']
    assert result['ev'] == pytest.approx((.6*1.9)**2-1)
    assert result['positive_return_probability'] == pytest.approx(.36)
    assert result['executable_quote_verified'] is False
    assert result['kelly']['recommended_fraction'] <= .02


def test_parlay_push_refunds_are_not_treated_as_losses():
    p = PayoutProbabilities(full_win=.35,push=.4,full_loss=.25)
    a,b = leg(payout=p,odds=2,market='ou',side='over',q=8), leg('event-2',payout=p,odds=2,market='ou',side='over',q=8)
    result = evaluate_parlay([a,b], now=NOW)
    assert result['eligible']
    assert result['ev'] == pytest.approx(1.1**2-1)
    assert result['positive_return_probability'] == pytest.approx(.35**2+2*.35*.4)
    assert result['all_legs_positive_probability'] == pytest.approx(.35**2)


def test_same_game_contradiction_is_blocked_without_independence_claim():
    result = evaluate_parlay([leg(),leg(market='ah',side='away',q=-2)],now=NOW,
                             fixture_distributions={'event-1':build_score_matrix(1.5,1.1)})
    assert not result['eligible'] and 'PARLAY_CONTRADICTION' in result['reason_codes']
    assert result['ev'] is None and result['positive_return_probability'] is None
    assert result['same_match_scenarios'][0]['positive_return_probability'] == 0


def test_positive_correlation_is_not_a_verified_joint_price():
    a,b = leg(),leg(market='ou',side='over',q=10)
    result = evaluate_parlay([a,b], now=NOW,fixture_distributions={'event-1':build_score_matrix(1.5,1.1)})
    assert result['reason_codes'] == ['SAME_MATCH_JOINT_PRICE_UNVERIFIED']
    assert result['same_match_scenarios'][0]['status'] == 'unvalidated_model_scenario'
    assert not result['eligible']


@pytest.mark.parametrize('mutation,reason', [
    ('quote','QUOTE_EXPIRED'),('reference','REFERENCE_EVIDENCE_UNAVAILABLE'),
    ('negative','PARLAY_LEG_EV_NOT_ABOVE_2_PERCENT'),('quant','PARLAY_LEG_NOT_VALUE')])
def test_parlay_rechecks_server_evidence(mutation,reason):
    a,b = leg(),leg('event-2')
    if mutation=='quote': a['quote_captured_at'] = NOW-400
    if mutation=='reference': a['quant']['reference_evidence']['source_updated_at'] = NOW-3600
    if mutation=='negative': a['payout'] = PayoutProbabilities(full_win=.4, full_loss=.6).__dict__
    if mutation=='quant': a['quant']['status'] = 'forecast'
    result = evaluate_parlay([a,b],now=NOW)
    assert not result['eligible'] and reason in result['reason_codes']


def test_builder_omits_negative_and_duplicate_event_legs():
    bad = leg('bad',payout=PayoutProbabilities(full_win=.4,full_loss=.6))
    results = build_value_parlays([leg(),leg('event-2'),bad],now=NOW)
    assert len(results)==1
    assert {l['event_key'] for l in results[0]['legs']} == {'event-1','event-2'}


def test_ledger_retains_displayed_confidence_and_versions_and_scores_matching_event():
    log = runpy.run_path(str(ROOT/'scripts/fc-log-projections.py'))
    grade = runpy.run_path(str(ROOT/'scripts/fc-grade-projections.py'))
    pick = {'market':'ah','side':'home','line_quarters':1,'pick':'AH Home +0.25','odds':1.9,
            'probability':.6,'confidence':.67,'confidence_source':'sharp','confidence_tier':'TINGGI',
            'formula_version':'v1','policy_version':'p1','quant':{'schema_version':'fc-quant-v1'}}
    match = {'info':{'match_id':'1','home':'H','away':'A','start_ts':NOW+7200},'projections':[pick]}
    first=log['collect_rows']([match], '2026-01-01T00:00:00Z')[0]
    pick['formula_version']='v2'
    second=log['collect_rows']([match], '2026-01-01T00:00:01Z')[0]
    assert first['ledger_id'] != second['ledger_id']
    assert first['confidence']==.67 and first['probability']==.6
    grades=[{'ledger_id':p['ledger_id'],'market':'ah','outcome':'half_win','model_probability':.6}
            for p in (first,second)]
    result=grade['build_report']([first,second],grades)
    assert len(result['calibration_cohorts'])==2
    assert {c['formula_version'] for c in result['calibration_cohorts']}=={'v1','v2'}
    assert all(c['brier']==pytest.approx(.16) for c in result['calibration_cohorts'])
