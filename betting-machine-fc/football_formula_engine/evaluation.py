"""Leakage-safe chronological evaluation for the Phase 4 football model."""
import copy
import hashlib
import json
import math
import re

from .baseline import fit_ratio_baseline
from .calibration import calibrate_distribution, fit_coherent_tilt, identity_calibration
from .contracts import ContractError, require
from .data import matches_as_of
from .markets import btts, match_odds, over_under
from .metrics import evaluate_prediction_records
from .model import FitConfig, build_ratio_baseline_artifact, fit_dixon_coles, project_fixture
from .score_matrix import build_score_matrix


EVALUATION_SCHEMA = 'fc-evaluation-report-v1'
PREDICTION_SCHEMA = 'fc-fold-predictions-v1'


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def seal(kind, content):
    digest = hashlib.sha256(canonical_bytes(content)).hexdigest()
    return {'artifact_id': f'{kind}-{digest[:16]}', 'content_sha256': digest, **content}


def validate_sealed_artifact(artifact, *, kind, schema_version):
    require(type(artifact) is dict and artifact.get('schema_version') == schema_version,
            'Unexpected sealed artifact schema')
    require(type(artifact.get('artifact_id')) is str
            and type(artifact.get('content_sha256')) is str
            and re.fullmatch(r'[a-f0-9]{64}', artifact['content_sha256']),
            'Invalid sealed artifact identity')
    content = {key: value for key, value in artifact.items()
               if key not in ('artifact_id', 'content_sha256')}
    digest = hashlib.sha256(canonical_bytes(content)).hexdigest()
    require(digest == artifact['content_sha256'], 'Sealed artifact hash mismatch')
    require(artifact['artifact_id'] == f'{kind}-{digest[:16]}', 'Sealed artifact ID mismatch')
    return artifact


def _validate_spec(spec):
    require(type(spec) is dict and spec.get('schema_version') == 'fc-evaluation-spec-v1',
            'Invalid evaluation spec')
    require(spec.get('official_enabled') is False, 'Evaluation cannot enable official')
    require(spec.get('candidate_half_life_days') == [90, 180, 365],
            'Unexpected half-life search space')
    require(type(spec.get('candidate_tilt_l2')) is list and spec['candidate_tilt_l2'],
            'Missing calibration penalty candidates')
    require(spec.get('primary_selection_metric') == 'score_log_loss',
            'Primary selection metric must stay frozen')
    require(set(spec.get('splits', {})) == {'calibration', 'policy_validation', 'untouched_test'},
            'Evaluation split set is incomplete')
    return spec


def _season_matches(matches, season):
    result = sorted((match for match in matches if match.season == season),
                    key=lambda match: (match.kickoff_utc, match.fixture_id))
    require(result, f'No matches for season {season}')
    return result


def resolve_split(matches, split_spec):
    season = _season_matches(matches, split_spec['season'])
    warmup = split_spec['warmup_matches']
    start, end = split_spec['start_index'], split_spec['end_index']
    require(type(warmup) is int and type(start) is int and type(end) is int
            and 0 < warmup == start < end <= len(season), 'Invalid chronological split indices')
    cutoff = season[warmup - 1].result_available_at_utc
    require(type(cutoff) is int, 'Warmup result availability missing')
    target = tuple(season[start:end])
    require(all(match.kickoff_utc > cutoff for match in target),
            'Split boundary leaks a same-time result into prediction')
    return cutoff, target


def _record(match, distribution, *, model_label, model_artifact_id,
            calibration_id, projection_status, reason_codes):
    require(match.home_goals <= distribution.max_goals
            and match.away_goals <= distribution.max_goals,
            'Observed score is outside projection grid')
    one_x_two = match_odds(distribution)
    both = btts(distribution)
    total = over_under(distribution, 'over', 10)
    return {
        'fixture_id': match.fixture_id,
        'season': match.season,
        'kickoff_utc': match.kickoff_utc,
        'actual_home': match.home_goals,
        'actual_away': match.away_goals,
        'score_probability': distribution.probabilities[match.home_goals][match.away_goals],
        'probabilities': {
            '1x2': {side: one_x_two[side].full_win for side in ('home', 'draw', 'away')},
            'btts_yes': both['yes'].full_win,
            'ou25_over': total.full_win,
        },
        'lambda_home': distribution.lambda_home,
        'lambda_away': distribution.lambda_away,
        'rho': distribution.rho,
        'max_goals': distribution.max_goals,
        'tail_mass_bound': distribution.tail_mass_bound,
        'model_label': model_label,
        'model_artifact_id': model_artifact_id,
        'calibration_id': calibration_id,
        'projection_status': projection_status,
        'reason_codes': list(reason_codes),
    }


def _artifact_distributions(artifact, target, *, calibration=None, force_rho_zero=False):
    rows, distributions, outcomes, blocked, ood = [], [], [], [], 0
    for match in target:
        projection = project_fixture(
            artifact, home_team_id=match.home_team_id, away_team_id=match.away_team_id,
            season=match.season)
        if projection.distribution is None:
            blocked.append({'fixture_id': match.fixture_id, 'status': projection.status,
                            'reason_codes': list(projection.reason_codes)})
            continue
        distribution = projection.distribution
        if force_rho_zero:
            distribution = build_score_matrix(projection.lambda_home, projection.lambda_away, 0.0)
        if calibration is not None:
            distribution = calibrate_distribution(distribution, calibration)
        if projection.status == 'projection_only_out_of_domain':
            ood += 1
        rows.append((match, distribution, projection.status, projection.reason_codes))
        distributions.append(distribution)
        outcomes.append((match.home_goals, match.away_goals))
    return rows, tuple(distributions), tuple(outcomes), blocked, ood


def _league_average_rows(matches, cutoff, target):
    training = matches_as_of(matches, cutoff)
    require(training, 'League-average training is empty')
    home_rate = sum(match.home_goals for match in training) / len(training)
    away_rate = sum(match.away_goals for match in training) / len(training)
    distribution = build_score_matrix(home_rate, away_rate, 0.0)
    return [(match, distribution, 'projection_ready_unvalidated', ()) for match in target]


def _records(rows, *, model_label, artifact_id, calibration_id):
    return [_record(match, distribution, model_label=model_label,
                    model_artifact_id=artifact_id, calibration_id=calibration_id,
                    projection_status=status, reason_codes=reasons)
            for match, distribution, status, reasons in rows]


def _prediction_artifact(split, label, records, *, cutoff, spec_hash):
    return seal('predictions', {
        'schema_version': PREDICTION_SCHEMA,
        'split': split,
        'model_label': label,
        'training_cutoff_utc': cutoff,
        'evaluation_spec_sha256': spec_hash,
        'prediction_count': len(records),
        'records': records,
    })


def run_chronological_evaluation(matches, spec):
    spec = copy.deepcopy(_validate_spec(spec))
    matches = tuple(matches)
    require({match.competition_id for match in matches} == {spec['competition_id']},
            'Evaluation competition mismatch')
    spec_hash = hashlib.sha256(canonical_bytes(spec)).hexdigest()
    calibration_cutoff, calibration_target = resolve_split(matches, spec['splits']['calibration'])
    policy_cutoff, policy_target = resolve_split(matches, spec['splits']['policy_validation'])
    test_cutoff, test_target = resolve_split(matches, spec['splits']['untouched_test'])
    require(calibration_cutoff < min(match.kickoff_utc for match in calibration_target)
            < policy_cutoff < min(match.kickoff_utc for match in policy_target)
            < test_cutoff < min(match.kickoff_utc for match in test_target),
            'Chronological split order is invalid')

    identity = identity_calibration()
    calibration_models, calibration_candidates = {}, []
    for half_life in spec['candidate_half_life_days']:
        config = FitConfig(half_life_days=half_life)
        artifact = fit_dixon_coles(matches, cutoff_utc=calibration_cutoff, config=config)
        rows, distributions, outcomes, blocked, ood = _artifact_distributions(
            artifact, calibration_target)
        require(not blocked and len(distributions) == len(calibration_target),
                'Calibration fold has blocked predictions')
        raw_records = _records(rows, model_label=f'dc_h{half_life}_identity',
                               artifact_id=artifact['artifact_id'],
                               calibration_id=identity['calibration_id'])
        calibration_models[half_life] = {
            'model_artifact': artifact,
            'identity_metrics': evaluate_prediction_records(
                raw_records, bin_count=spec['reliability_bins']),
            'distributions': distributions,
            'outcomes': outcomes,
            'ood_count': ood,
        }
        calibration_candidates.append({
            'half_life_days': half_life, 'calibration_method': 'identity',
            'calibration_artifact': identity,
            'fit_metrics': calibration_models[half_life]['identity_metrics'],
        })
        for l2 in spec['candidate_tilt_l2']:
            calibration = fit_coherent_tilt(distributions, outcomes, l2=l2)
            tilted_rows = [(row[0], calibrate_distribution(row[1], calibration), row[2], row[3])
                           for row in rows]
            records = _records(tilted_rows, model_label=f'dc_h{half_life}_tilt_l2_{l2:g}',
                               artifact_id=artifact['artifact_id'],
                               calibration_id=calibration['calibration_id'])
            calibration_candidates.append({
                'half_life_days': half_life, 'calibration_method': 'coherent_exponential_tilt',
                'tilt_l2': l2, 'calibration_artifact': calibration,
                'fit_metrics': evaluate_prediction_records(
                    records, bin_count=spec['reliability_bins']),
            })

    policy_results = []
    policy_artifacts = {}
    for half_life in spec['candidate_half_life_days']:
        artifact = fit_dixon_coles(
            matches, cutoff_utc=policy_cutoff, config=FitConfig(half_life_days=half_life))
        policy_artifacts[half_life] = artifact
        candidates = [candidate for candidate in calibration_candidates
                      if candidate['half_life_days'] == half_life]
        for candidate in candidates:
            calibration = candidate['calibration_artifact']
            rows, _, _, blocked, ood = _artifact_distributions(
                artifact, policy_target, calibration=calibration)
            records = _records(
                rows,
                model_label=(f'dc_h{half_life}_identity' if candidate['calibration_method'] == 'identity'
                             else f"dc_h{half_life}_tilt_l2_{candidate['tilt_l2']:g}"),
                artifact_id=artifact['artifact_id'],
                calibration_id=calibration['calibration_id'])
            require(len(records) == len(policy_target) and not blocked,
                    'Policy fold has blocked predictions')
            policy_results.append({
                'half_life_days': half_life,
                'calibration_method': candidate['calibration_method'],
                'tilt_l2': candidate.get('tilt_l2'),
                'calibration_artifact': calibration,
                'model_artifact_id': artifact['artifact_id'],
                'metrics': evaluate_prediction_records(records, bin_count=spec['reliability_bins']),
                'blocked_count': len(blocked), 'out_of_domain_count': ood,
            })
    policy_results.sort(key=lambda item: (
        item['metrics'][spec['primary_selection_metric']], item['half_life_days'],
        item['calibration_method'], item['tilt_l2'] or 0))
    selected = policy_results[0]
    selected_half_life = selected['half_life_days']
    selected_calibration = selected['calibration_artifact']

    test_dc = fit_dixon_coles(
        matches, cutoff_utc=test_cutoff, config=FitConfig(half_life_days=selected_half_life))
    test_ratio = build_ratio_baseline_artifact(matches, cutoff_utc=test_cutoff)
    test_models = {}

    league_rows = _league_average_rows(matches, test_cutoff, test_target)
    league_records = _records(league_rows, model_label='league_average_poisson',
                              artifact_id='league-average-at-cutoff',
                              calibration_id=identity['calibration_id'])
    test_models['league_average_poisson'] = league_records

    ratio_rows, _, _, ratio_blocked, _ = _artifact_distributions(test_ratio, test_target)
    require(not ratio_blocked, 'Ratio baseline has blocked test predictions')
    test_models['ratio_baseline'] = _records(
        ratio_rows, model_label='ratio_baseline', artifact_id=test_ratio['artifact_id'],
        calibration_id=identity['calibration_id'])

    independent_rows, _, _, independent_blocked, _ = _artifact_distributions(
        test_dc, test_target, force_rho_zero=True)
    require(not independent_blocked, 'Independent Poisson ablation has blocked predictions')
    test_models['regularized_independent_poisson'] = _records(
        independent_rows, model_label='regularized_independent_poisson',
        artifact_id=test_dc['artifact_id'], calibration_id=identity['calibration_id'])

    identity_rows, _, _, identity_blocked, _ = _artifact_distributions(test_dc, test_target)
    require(not identity_blocked, 'DC identity has blocked test predictions')
    test_models['dixon_coles_identity'] = _records(
        identity_rows, model_label='dixon_coles_identity', artifact_id=test_dc['artifact_id'],
        calibration_id=identity['calibration_id'])

    selected_rows, _, _, selected_blocked, selected_ood = _artifact_distributions(
        test_dc, test_target, calibration=selected_calibration)
    require(not selected_blocked, 'Selected candidate has blocked test predictions')
    selected_label = ('dixon_coles_identity' if selected['calibration_method'] == 'identity'
                      else 'dixon_coles_coherent_tilt')
    test_models['selected_candidate'] = _records(
        selected_rows, model_label=selected_label, artifact_id=test_dc['artifact_id'],
        calibration_id=selected_calibration['calibration_id'])

    test_metrics = {label: evaluate_prediction_records(records, bin_count=spec['reliability_bins'])
                    for label, records in test_models.items()}
    primary = spec['primary_selection_metric']
    primary_improved = test_metrics['selected_candidate'][primary] < test_metrics['ratio_baseline'][primary]
    quality_gate = {
        'minimum_test_matches': len(test_target) >= spec['quality_gate']['minimum_test_matches'],
        'primary_improvement_vs_ratio_baseline': primary_improved,
        'multiple_outer_periods': False,
        'reliable_uncertainty': False,
        'timed_executable_quotes_for_roi': False,
    }
    quality_gate['approved'] = all(quality_gate.values())

    prediction_artifacts = {
        label: _prediction_artifact('untouched_test', label, records,
                                    cutoff=test_cutoff, spec_hash=spec_hash)
        for label, records in test_models.items()
    }
    report = seal('evaluation', {
        'schema_version': EVALUATION_SCHEMA,
        'evaluation_spec_sha256': spec_hash,
        'competition_id': spec['competition_id'],
        'coverage_status': spec['coverage_status'],
        'split_summary': {
            'calibration': {'training_cutoff_utc': calibration_cutoff,
                            'prediction_count': len(calibration_target)},
            'policy_validation': {'training_cutoff_utc': policy_cutoff,
                                  'prediction_count': len(policy_target)},
            'untouched_test': {'training_cutoff_utc': test_cutoff,
                               'prediction_count': len(test_target)},
        },
        'selection': {
            'selected_on': 'policy_validation',
            'primary_metric': primary,
            'half_life_days': selected_half_life,
            'calibration_method': selected['calibration_method'],
            'tilt_l2': selected.get('tilt_l2'),
            'calibration_artifact': selected_calibration,
            'policy_primary_score': selected['metrics'][primary],
            'candidate_count': len(policy_results),
        },
        'policy_candidates': policy_results,
        'test_model_artifact_id': test_dc['artifact_id'],
        'test_ratio_artifact_id': test_ratio['artifact_id'],
        'test_metrics': test_metrics,
        'test_prediction_artifact_ids': {
            label: artifact['artifact_id'] for label, artifact in prediction_artifacts.items()},
        'test_out_of_domain_count': selected_ood,
        'quality_gate': quality_gate,
        'uncertainty_status': 'PENDING_PHASE5C',
        'roi_status': spec['roi_status'],
        'clv_status': spec['clv_status'],
        'ah_status': spec['ah_status'],
        'validation_status': 'not_approved',
        'official_enabled': False,
        'limitations': [
            spec['coverage_note'],
            'Only one untouched outer test period is available in the local dataset',
            'Historical quotes have no defensible decision timestamps, so ROI and CLV are not evaluated',
            'Test results are reporting evidence and must not be used to retune this run',
        ],
    })
    return {
        'report': report,
        'prediction_artifacts': prediction_artifacts,
        'test_model_artifact': test_dc,
        'test_ratio_artifact': test_ratio,
        'selected_calibration_artifact': selected_calibration,
    }
