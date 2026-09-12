"""Strict stdlib v2 boundary, paired with lib/fc/contracts-v2.ts and shared vectors.

Validation is structural evidence checking, not proof of model approval, freshness,
an authentic hash, or an immutable lock. Production adapters must establish those.
"""
import math
import re


class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def object_fields(value, names):
    require(type(value) is dict and set(value) == set(names.split()), 'Invalid object fields')


def identifier(value):
    require(type(value) is str and bool(value) and value == value.strip(), 'Invalid identifier')


def number(value):
    require(type(value) in (int, float), 'Invalid number type')
    try:
        require(math.isfinite(value), 'Invalid finite number')
    except OverflowError as exc:
        raise ContractError('Number out of range') from exc


def integer(value):
    number(value)
    require(value == int(value) and abs(value) <= 9007199254740991, 'Invalid safe integer')


def timestamp(value):
    integer(value)
    require(0 <= value <= 4102444800, 'Invalid UTC seconds')


def choice(value, options):
    require(type(value) is str and value in options.split(), 'Invalid enum')


def validate_snapshot(v):
    object_fields(v, 'schema_version run_id decision_at fixture contract quote prediction decision capabilities diagnostics')
    require(v['schema_version'] == 'fc-contract-v2', 'Unknown schema')
    identifier(v['run_id'])
    timestamp(v['decision_at'])
    f, c, q, p, d, caps = (v[k] for k in ('fixture', 'contract', 'quote', 'prediction', 'decision', 'capabilities'))
    object_fields(f, 'fixture_id competition_id season home_team_id away_team_id kickoff_utc')
    for k in ('fixture_id', 'competition_id', 'season', 'home_team_id', 'away_team_id'):
        identifier(f[k])
    timestamp(f['kickoff_utc'])
    require(f['home_team_id'] != f['away_team_id'], 'Teams must differ')
    object_fields(c, 'contract_id fixture_id market side line_quarters period')
    for k in ('contract_id', 'fixture_id'):
        identifier(c[k])
    choice(c['market'], '1x2 ou ah btts')
    choice(c['side'], {'1x2': 'home draw away', 'ou': 'over under', 'ah': 'home away', 'btts': 'yes no'}[c['market']])
    require(c['period'] == 'regulation', 'Unsupported period')
    require(c['fixture_id'] == f['fixture_id'], 'Fixture reference mismatch')
    if c['market'] in ('ou', 'ah'):
        integer(c['line_quarters'])
        require(c['market'] != 'ou' or c['line_quarters'] >= 0, 'Negative total')
    else:
        require(c['line_quarters'] is None, 'Unexpected line')
    if q is not None:
        object_fields(q, 'quote_id contract_id provider bookmaker captured_at available_at decimal_odds freshness is_closing')
        for k in ('quote_id', 'contract_id', 'provider', 'bookmaker'):
            identifier(q[k])
        for k in ('captured_at', 'available_at'):
            timestamp(q[k])
        number(q['decimal_odds'])
        require(q['decimal_odds'] > 1, 'Invalid odds')
        choice(q['freshness'], 'fresh stale unknown')
        require(type(q['is_closing']) is bool, 'Invalid closing flag')
        require(q['contract_id'] == c['contract_id'], 'Quote reference mismatch')
        require(q['available_at'] <= q['captured_at'] <= v['decision_at'], 'Invalid quote time')
    if p is not None:
        object_fields(p, 'prediction_id contract_id formula_version calibration_version data_hash training_cutoff payout ev_net ev_lower uncertainty_status validation_status')
        for k in ('prediction_id', 'contract_id', 'formula_version', 'calibration_version'):
            identifier(p[k])
        require(type(p['data_hash']) is str and re.fullmatch('[a-f0-9]{64}', p['data_hash']) is not None, 'Invalid hash')
        timestamp(p['training_cutoff'])
        require(p['training_cutoff'] <= v['decision_at'], 'Future training cutoff')
        require(p['contract_id'] == c['contract_id'], 'Prediction reference mismatch')
        object_fields(p['payout'], 'full_win half_win push half_loss full_loss')
        for prob in p['payout'].values():
            number(prob)
            require(0 <= prob <= 1, 'Invalid probability')
        require(abs(sum(p['payout'].values()) - 1) <= 1e-8, 'Invalid payout mass')
        number(p['ev_net'])
        if p['ev_lower'] is not None:
            number(p['ev_lower'])
        choice(p['uncertainty_status'], 'available unavailable')
        choice(p['validation_status'], 'unvalidated approved')
        require((p['uncertainty_status'] == 'available') == (p['ev_lower'] is not None), 'Uncertainty mismatch')
    object_fields(d, 'status policy_version is_top_pick reason_codes')
    choice(d['status'], 'projection_only paper_candidate official_candidate official_locked blocked')
    identifier(d['policy_version'])
    require(type(d['is_top_pick']) is bool and type(d['reason_codes']) is list, 'Invalid decision')
    for reason in d['reason_codes']:
        identifier(reason)
    require(d['status'] != 'blocked' or bool(d['reason_codes']), 'Blocked reason required')
    object_fields(caps, 'schedule_available prediction_available model_validated official_enabled')
    require(all(type(flag) is bool for flag in caps.values()), 'Invalid capability')
    require(caps['prediction_available'] == (p is not None), 'Prediction capability mismatch')
    require(caps['model_validated'] == (p is not None and p['validation_status'] == 'approved'), 'Validation capability mismatch')
    official = d['status'] in ('official_candidate', 'official_locked')
    require(not d['is_top_pick'] or official, 'Top pick must be official')
    if official or d['status'] == 'paper_candidate':
        require(p is not None and q is not None and q['freshness'] == 'fresh', 'Candidate evidence incomplete')
        require(v['decision_at'] < f['kickoff_utc'] and p['ev_lower'] is not None and p['ev_lower'] > 0, 'Candidate time/EV invalid')
    require(not official or (caps['official_enabled'] and caps['model_validated']), 'Official gate closed')
    require(type(v['diagnostics']) is list, 'Invalid diagnostics')
    for diagnostic in v['diagnostics']:
        object_fields(diagnostic, 'code message')
        choice(diagnostic['code'], 'missing corrupt invalid stale unavailable')
        identifier(diagnostic['message'])
    return v
