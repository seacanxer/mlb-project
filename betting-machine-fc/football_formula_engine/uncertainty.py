"""Moving-block refit uncertainty with append-only per-replicate checkpoints."""
import hashlib
import math
import random

import numpy as np

from .calibration import fit_coherent_tilt, identity_calibration
from .contracts import ContractError, require
from .data import matches_as_of
from .evaluation import (_artifact_distributions, _records, canonical_bytes,
                         resolve_split, seal, validate_sealed_artifact)
from .metrics import evaluate_prediction_records
from .model import FitConfig, fit_dixon_coles


BOOTSTRAP_SCHEMA = 'fc-bootstrap-replicate-v1'
UNCERTAINTY_SCHEMA = 'fc-uncertainty-report-v1'


def moving_block_sample(matches, *, block_length, seed):
    matches = tuple(sorted(matches, key=lambda match: (match.kickoff_utc, match.fixture_id)))
    require(matches and type(block_length) is int and 1 <= block_length <= len(matches),
            'Invalid moving-block input')
    rng = random.Random(seed)
    starts, sampled = [], []
    maximum_start = len(matches) - block_length
    while len(sampled) < len(matches):
        start = rng.randint(0, maximum_start)
        starts.append(start)
        sampled.extend(matches[start:start + block_length])
    return tuple(sampled[:len(matches)]), starts


def run_bootstrap_replicate(matches, spec, evaluation_report, replicate_index):
    bootstrap = spec['bootstrap']
    require(type(replicate_index) is int and 0 <= replicate_index < bootstrap['replicates'],
            'Invalid bootstrap replicate')
    selected = evaluation_report['selection']
    half_life = selected['half_life_days']
    test_cutoff, test_target = resolve_split(matches, spec['splits']['untouched_test'])
    test_training = matches_as_of(matches, test_cutoff)
    seed = bootstrap['seed'] + replicate_index
    sampled_test, test_starts = moving_block_sample(
        test_training, block_length=bootstrap['block_length_matches'], seed=seed)
    calibration = identity_calibration()
    calibration_starts = []
    if selected['calibration_method'] == 'coherent_exponential_tilt':
        calibration_cutoff, calibration_target = resolve_split(
            matches, spec['splits']['calibration'])
        calibration_training = matches_as_of(matches, calibration_cutoff)
        sampled_calibration, calibration_starts = moving_block_sample(
            calibration_training, block_length=min(bootstrap['block_length_matches'],
                                                     len(calibration_training)),
            seed=seed + 1_000_000)
        calibration_model = fit_dixon_coles(
            sampled_calibration, cutoff_utc=calibration_cutoff,
            config=FitConfig(half_life_days=half_life))
        _, distributions, outcomes, blocked, _ = _artifact_distributions(
            calibration_model, calibration_target)
        require(not blocked and len(distributions) == len(calibration_target),
                'Bootstrap calibration projection failed')
        calibration = fit_coherent_tilt(
            distributions, outcomes, l2=selected['tilt_l2'])

    model = fit_dixon_coles(
        sampled_test, cutoff_utc=test_cutoff, config=FitConfig(half_life_days=half_life))
    rows, _, _, blocked, ood = _artifact_distributions(
        model, test_target, calibration=calibration)
    require(not blocked and len(rows) == len(test_target),
            'Bootstrap test projection failed')
    records = _records(rows, model_label='bootstrap_selected_candidate',
                       artifact_id=model['artifact_id'],
                       calibration_id=calibration['calibration_id'])
    sample_fingerprint = hashlib.sha256(canonical_bytes({
        'test_block_starts': test_starts,
        'calibration_block_starts': calibration_starts,
    })).hexdigest()
    return seal('bootstrap', {
        'schema_version': BOOTSTRAP_SCHEMA,
        'evaluation_id': evaluation_report['artifact_id'],
        'replicate_index': replicate_index,
        'seed': seed,
        'method': bootstrap['method'],
        'block_length_matches': bootstrap['block_length_matches'],
        'sample_fingerprint': sample_fingerprint,
        'model_artifact_id': model['artifact_id'],
        'calibration_id': calibration['calibration_id'],
        'out_of_domain_count': ood,
        'metrics': evaluate_prediction_records(records, bin_count=spec['reliability_bins']),
        'fixture_probabilities': [{
            'fixture_id': record['fixture_id'],
            'btts_yes': record['probabilities']['btts_yes'],
            'ou25_over': record['probabilities']['ou25_over'],
            'home': record['probabilities']['1x2']['home'],
            'draw': record['probabilities']['1x2']['draw'],
            'away': record['probabilities']['1x2']['away'],
        } for record in records],
    })


def summarize_uncertainty(spec, evaluation_report, replicates):
    replicates = sorted(replicates, key=lambda value: value['replicate_index'])
    require(replicates, 'No successful bootstrap replicates')
    for replicate in replicates:
        validate_sealed_artifact(replicate, kind='bootstrap', schema_version=BOOTSTRAP_SCHEMA)
        require(replicate['evaluation_id'] == evaluation_report['artifact_id'],
                'Bootstrap belongs to another evaluation')
    require(len({value['replicate_index'] for value in replicates}) == len(replicates),
            'Duplicate bootstrap replicate')
    quantiles = spec['bootstrap']['quantiles']

    def q(values):
        return {str(level): round(float(np.quantile(values, level)), 12) for level in quantiles}

    metric_names = ('score_log_loss', '1x2_brier', 'btts_brier', 'ou25_brier')
    metric_quantiles = {name: q([replicate['metrics'][name] for replicate in replicates])
                        for name in metric_names}
    by_fixture = {}
    for replicate in replicates:
        for row in replicate['fixture_probabilities']:
            target = by_fixture.setdefault(row['fixture_id'], {
                'btts_yes': [], 'ou25_over': [], 'home': [], 'draw': [], 'away': []})
            for key in target:
                target[key].append(row[key])
    fixture_quantiles = {
        fixture_id: {key: q(values) for key, values in probabilities.items()}
        for fixture_id, probabilities in sorted(by_fixture.items())
    }
    reliable = len(replicates) >= spec['bootstrap']['minimum_reliable_replicates']
    return seal('uncertainty', {
        'schema_version': UNCERTAINTY_SCHEMA,
        'evaluation_id': evaluation_report['artifact_id'],
        'method': spec['bootstrap']['method'],
        'requested_replicates': spec['bootstrap']['replicates'],
        'successful_replicates': len(replicates),
        'minimum_reliable_replicates': spec['bootstrap']['minimum_reliable_replicates'],
        'status': 'AVAILABLE' if reliable else 'UNCERTAINTY_UNAVAILABLE_INSUFFICIENT_REPLICATES',
        'metric_quantiles': metric_quantiles,
        'fixture_probability_quantiles': fixture_quantiles,
        'replicate_artifact_ids': [replicate['artifact_id'] for replicate in replicates],
        'official_eligible': False,
        'limitation': ('Smoke bootstrap verifies refit/checkpoint plumbing; it is not a confidence interval '
                       'for betting profitability and does not use the untouched test for tuning'),
    })


def build_validation_registry(spec, evaluation_report, uncertainty_report):
    test = evaluation_report['test_metrics']
    selected = test['selected_candidate']
    league = test['league_average_poisson']
    shared_reasons = ['SINGLE_OUTER_PERIOD', 'UNCERTAINTY_UNAVAILABLE', 'ROI_NOT_EVALUABLE']
    btts_reasons = list(shared_reasons)
    ou_reasons = list(shared_reasons)
    if selected['btts_brier'] >= league['btts_brier']:
        btts_reasons.insert(0, 'WORSE_THAN_LEAGUE_AVERAGE_BASELINE')
    if selected['ou25_brier'] >= league['ou25_brier']:
        ou_reasons.insert(0, 'WORSE_THAN_LEAGUE_AVERAGE_BASELINE')
    segments = {
        '1x2': {
            'status': 'paper_only_not_approved',
            'selected_brier': selected['1x2_brier'],
            'league_average_brier': league['1x2_brier'],
            'reason_codes': list(shared_reasons),
        },
        'btts': {
            'status': 'not_approved',
            'selected_brier': selected['btts_brier'],
            'league_average_brier': league['btts_brier'],
            'reason_codes': btts_reasons,
        },
        'ou_2_5': {
            'status': 'not_approved',
            'selected_brier': selected['ou25_brier'],
            'league_average_brier': league['ou25_brier'],
            'reason_codes': ou_reasons,
        },
        'ah': {
            'status': 'not_evaluated',
            'reason_codes': ['PAYOUT_AWARE_REFERENCE_NOT_IMPLEMENTED', 'ROI_NOT_EVALUABLE'],
        },
    }
    return seal('validation', {
        'schema_version': 'fc-model-validation-registry-v1',
        'evaluation_id': evaluation_report['artifact_id'],
        'uncertainty_id': uncertainty_report['artifact_id'],
        'selected_configuration': evaluation_report['selection'],
        'segments': segments,
        'overall_status': 'not_approved',
        'quality_gate': {**evaluation_report['quality_gate'],
                         'reliable_uncertainty': uncertainty_report['status'] == 'AVAILABLE',
                         'approved': False},
        'roi_status': spec['roi_status'],
        'clv_status': spec['clv_status'],
        'official_enabled': False,
        'next_action': 'Collect a third season and timed executable quotes, then run a newly preregistered evaluation',
    })
