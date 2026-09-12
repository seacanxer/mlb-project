import copy
import json
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
from football_formula_engine.contracts import ContractError
from football_formula_engine.ledger import PaperLedger
from football_formula_engine.policy import select_candidates


def source():
    s = json.loads((ROOT / 'tests/fixtures/fc-v2-contract.json').read_text())
    s['diagnostics'] = []
    return s


def evidence(s):
    return {s['prediction']['prediction_id']: {
        'snapshot': copy.deepcopy(s),
        'segment': [s['fixture']['competition_id'], s['contract']['market'], s['contract']['line_quarters']],
        'validation_status': 'approved', 'uncertainty_status': 'available',
        'payout_samples': [copy.deepcopy(s['prediction']['payout']) for _ in range(30)]}}


def candidate():
    s = source()
    return select_candidates([s], evidence(s), decision_at=s['decision_at'])['selected'][0]


def event(s, **changes):
    return dict(event_id='final-1', fixture_id=s['fixture']['fixture_id'], source='synthetic',
                observed_at=s['fixture']['kickoff_utc'] + 7200, status='final',
                home_goals=1, away_goals=0, reason='', **changes)


def test_phase5_has_no_approved_segments_and_policy_returns_no_bet():
    registry = json.loads((ROOT / 'betting-machine-fc/football_formula_engine/artifacts/phase5-validation-registry.json').read_text())
    assert 'approved' not in registry['segment_status'].values()
    s = source()
    result = select_candidates([s], {}, decision_at=s['decision_at'])
    assert result['status'] == 'NO_BET'
    assert result['selected'] == []
    assert result['decisions'][0]['prediction']['ev_lower'] is None


def test_reprices_bootstrap_and_limits_one_fixture_deterministically():
    a = source()
    b = copy.deepcopy(a)
    b['contract']['contract_id'] = 'other-contract'
    b['quote'].update(contract_id='other-contract', quote_id='other-quote', decimal_odds=2.1)
    b['prediction'].update(contract_id='other-contract', prediction_id='other-prediction')
    proof = {**evidence(a), **evidence(b)}
    result = select_candidates([a, b], proof, decision_at=a['decision_at'])
    assert len(result['selected']) == 1
    assert result['selected'][0]['quote']['decimal_odds'] == 2.1
    assert result['selected'][0]['prediction']['ev_lower'] == pytest.approx(.385)
    assert result['rejection_counts']['FIXTURE_EXPOSURE_LIMIT'] == 1
    assert not result['selected'][0]['decision']['is_top_pick']


@pytest.mark.parametrize('mutation', ['stale', 'missing_samples', 'changed_quote', 'wrong_segment', 'negative_edge'])
def test_evidence_and_quote_gates(mutation):
    s = source()
    proof = evidence(s)
    p = proof[s['prediction']['prediction_id']]
    if mutation == 'stale':
        return_value = select_candidates([s], proof, decision_at=s['decision_at'], max_age_seconds=1)
    else:
        if mutation == 'missing_samples': p['payout_samples'] = []
        if mutation == 'changed_quote': s['quote']['decimal_odds'] = 3
        if mutation == 'wrong_segment': p['segment'][2] = 10
        if mutation == 'negative_edge':
            p['payout_samples'] = [dict(full_win=0, half_win=0, push=0, half_loss=0, full_loss=1)] * 30
        return_value = select_candidates([s], proof, decision_at=s['decision_at'])
    assert return_value['status'] == 'NO_BET'


def test_lock_restart_conflict_and_revision_profit(tmp_path):
    path = tmp_path / 'paper.db'
    ledger = PaperLedger(path)
    s = candidate()
    lock = ledger.lock(s, locked_at=s['decision_at'])
    assert PaperLedger(path).lock(s, locked_at=s['decision_at'])['status'] == 'deduplicated'
    changed = copy.deepcopy(s)
    changed['quote']['decimal_odds'] = 4
    with pytest.raises(ContractError): ledger.lock(changed, locked_at=s['decision_at'])
    assert ledger.tracker()['roi'] is None
    first = event(s)
    assert ledger.settle(lock['bet_id'], first, expected_revision=0)['profit_units'] == pytest.approx(.475)
    assert ledger.settle(lock['bet_id'], first, expected_revision=0)['status'] == 'deduplicated'
    corrected = {**first, 'event_id': 'corrected', 'home_goals': 0, 'observed_at': first['observed_at'] + 10}
    with pytest.raises(ContractError): ledger.settle(lock['bet_id'], corrected, expected_revision=0)
    ledger.settle(lock['bet_id'], corrected, expected_revision=1)
    tracker = PaperLedger(path).tracker()
    assert tracker['profit_units'] == -1
    assert tracker['settled'] == 1
    assert tracker['revision_count'] == 2
    assert tracker['roi'] == -1
    assert ledger.settle(lock['bet_id'], first, expected_revision=0)['status'] == 'deduplicated'
    assert ledger.tracker()['profit_units'] == -1


def test_void_denominator_and_stale_correction(tmp_path):
    ledger = PaperLedger(tmp_path / 'paper.db')
    s = candidate()
    bet = ledger.lock(s, locked_at=s['decision_at'])['bet_id']
    result = {**event(s), 'status': 'void', 'home_goals': None, 'away_goals': None, 'reason': 'abandoned operator void'}
    ledger.settle(bet, result, expected_revision=0)
    assert ledger.tracker()['settled_stake_units'] == 1
    assert ledger.tracker()['roi'] == 0
    with pytest.raises(ContractError):
        ledger.settle(bet, {**event(s), 'event_id': 'stale'}, expected_revision=1)


def test_racing_locks_and_settlements_are_idempotent(tmp_path):
    path = tmp_path / 'paper.db'
    PaperLedger(path)
    s = candidate()
    with ThreadPoolExecutor(max_workers=4) as pool:
        locks = list(pool.map(lambda _: PaperLedger(path).lock(s, locked_at=s['decision_at']), range(4)))
    assert sum(x['status'] == 'created' for x in locks) == 1
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: PaperLedger(path).settle(locks[0]['bet_id'], event(s), expected_revision=0), range(4)))
    assert sum(x['status'] == 'settled' for x in results) == 1
    assert PaperLedger(path).tracker()['revision_count'] == 1


def test_failed_transaction_rolls_back(tmp_path):
    path = tmp_path / 'paper.db'
    ledger = PaperLedger(path)
    with pytest.raises(RuntimeError):
        with ledger._transaction() as db:
            db.execute('INSERT INTO paper_locks VALUES (?,?,?,?)', ('test', 'test', '{}', 0))
            raise RuntimeError('interrupted before commit')
    assert PaperLedger(path).tracker()['total'] == 0


@pytest.mark.parametrize('market,side,line,h,a,outcome,profit', [
    ('ah', 'home', -3, 2, 0, 'full_win', .95),
    ('ah', 'home', -3, 1, 0, 'half_win', .475),
    ('ah', 'home', 0, 1, 1, 'push', 0),
    ('ou', 'over', 9, 1, 1, 'half_loss', -.5),
    ('btts', 'yes', None, 1, 0, 'full_loss', -1),
    ('1x2', 'draw', None, 1, 1, 'full_win', .95),
])
def test_ledger_exact_payouts(tmp_path, market, side, line, h, a, outcome, profit):
    s = source()
    s['contract'].update(market=market, side=side, line_quarters=line)
    selected = select_candidates([s], evidence(s), decision_at=s['decision_at'])['selected'][0]
    ledger = PaperLedger(tmp_path / 'paper.db')
    bet = ledger.lock(selected, locked_at=s['decision_at'])['bet_id']
    result = ledger.settle(bet, {**event(s), 'home_goals': h, 'away_goals': a}, expected_revision=0)
    assert result['outcome'] == outcome
    assert ledger.tracker()['profit_units'] == pytest.approx(profit)
    assert ledger.tracker()['roi'] == pytest.approx(profit)


def test_process_exit_before_commit_preserves_previous_state(tmp_path):
    import subprocess
    path = tmp_path / 'paper.db'
    PaperLedger(path)
    program = "import sqlite3,sys,os; d=sqlite3.connect(sys.argv[1]); d.execute('BEGIN IMMEDIATE'); d.execute(\"INSERT INTO paper_locks VALUES ('crash','crash','{}',0)\"); os._exit(7)"
    result = subprocess.run([sys.executable, '-c', program, str(path)], check=False)
    assert result.returncode == 7
    assert PaperLedger(path).tracker()['total'] == 0
