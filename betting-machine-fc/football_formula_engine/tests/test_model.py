from dataclasses import replace
from pathlib import Path
import copy
import hashlib
import json
import math
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
from football_formula_engine.contracts import ContractError
from football_formula_engine.data import NormalizedMatch
from football_formula_engine.model import (
    FitConfig, build_ratio_baseline_artifact, fit_dixon_coles,
    project_fixture, validate_model_artifact,
)
from football_formula_engine.score_matrix import rho_bounds


def synthetic_matches():
    teams = ('A', 'B', 'C', 'D')
    scores = ((2, 0), (1, 1), (0, 1), (3, 1), (1, 0), (2, 2),
              (1, 2), (2, 1), (0, 0), (3, 0), (1, 1), (0, 2))
    values = []
    start = 1_700_000_000
    row = 0
    for cycle in range(3):
        for home in teams:
            for away in teams:
                if home == away:
                    continue
                goals = scores[row % len(scores)]
                kickoff = start + row * 5 * 86400
                values.append(NormalizedMatch(
                    fixture_id=f'f-{row}', competition_id='TEST', season='2324' if cycle == 0 else '2425',
                    home_team_id=home, away_team_id=away, home_team_name=home,
                    away_team_name=away, kickoff_utc=kickoff, result_status='final',
                    home_goals=goals[0], away_goals=goals[1],
                    result_available_at_utc=kickoff + 4 * 3600,
                    result_availability_basis='test', source='test', source_file='test.csv',
                    source_row=row + 2, raw_sha256=f'{row:064x}'))
                row += 1
    return tuple(values)


@pytest.fixture(scope='module')
def fitted():
    matches = synthetic_matches()
    cutoff = max(match.result_available_at_utc for match in matches)
    config = FitConfig(minimum_matches=20, minimum_team_matches=5, max_iterations=500)
    return matches, cutoff, config, fit_dixon_coles(matches, cutoff_utc=cutoff, config=config)


def test_fit_is_reproducible_and_unvalidated(fitted):
    matches, cutoff, config, first = fitted
    second = fit_dixon_coles(iter(matches), cutoff_utc=cutoff, config=config)
    assert first == second
    assert first['validation_status'] == 'unvalidated'
    assert first['official_eligible'] is False
    assert first['config']['half_life_selection_status'] == 'deferred_to_phase_5_inner_validation'
    validate_model_artifact(first)


def test_fit_enforces_identifiability_and_valid_training_rho(fitted):
    _, _, _, artifact = fitted
    teams = artifact['parameters']['team_effects'].values()
    assert sum(team['attack'] for team in teams) == pytest.approx(0, abs=1e-10)
    assert sum(team['defence_vulnerability'] for team in teams) == pytest.approx(0, abs=1e-10)
    diagnostics = artifact['diagnostics']
    assert diagnostics['rho_training_lower_bound'] <= artifact['parameters']['rho']
    assert artifact['parameters']['rho'] <= diagnostics['rho_training_upper_bound']
    assert 0 < diagnostics['effective_match_count'] <= artifact['training']['used_match_count']
    assert 0 < diagnostics['oldest_weight_relative_to_newest'] < 1


def test_future_result_does_not_change_parameters_or_training_hash(fitted):
    matches, cutoff, config, artifact = fitted
    future = replace(matches[-1], fixture_id='future', kickoff_utc=cutoff + 86400,
                     result_available_at_utc=cutoff + 86400 + 4 * 3600,
                     home_goals=20, away_goals=0)
    with_future = fit_dixon_coles(matches + (future,), cutoff_utc=cutoff, config=config)
    assert with_future == artifact


def test_one_inference_path_handles_ready_neutral_and_unseen(fitted):
    _, _, _, artifact = fitted
    regular = project_fixture(artifact, home_team_id='A', away_team_id='B', season='2425')
    neutral = project_fixture(artifact, home_team_id='A', away_team_id='B', season='2425', neutral=True)
    assert regular.status == 'projection_ready_unvalidated'
    assert regular.distribution is not None
    assert sum(probability for _, _, probability in regular.distribution.cells()) == pytest.approx(1)
    home_advantage = artifact['parameters']['season_effects']['2425']['home_advantage']
    assert regular.lambda_home / neutral.lambda_home == pytest.approx(math.exp(home_advantage), rel=1e-10)
    unseen = project_fixture(artifact, home_team_id='PROMOTED', away_team_id='B', season='2425')
    assert unseen.status == 'projection_only_out_of_domain'
    assert unseen.distribution is not None
    assert unseen.reason_codes == ('HOME_TEAM_OUT_OF_DOMAIN',)


def test_unknown_season_and_invalid_rho_fail_closed(fitted):
    _, _, _, artifact = fitted
    unknown = project_fixture(artifact, home_team_id='A', away_team_id='B', season='2526')
    assert unknown.status == 'projection_blocked'
    assert unknown.distribution is None
    tampered = copy.deepcopy(artifact)
    tampered['parameters']['rho'] = 5
    with pytest.raises(ContractError, match='hash mismatch'):
        project_fixture(tampered, home_team_id='A', away_team_id='B', season='2425')
    content = {key: value for key, value in tampered.items()
               if key not in ('artifact_id', 'content_sha256')}
    digest = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(',', ':'),
                                      ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    tampered['content_sha256'] = digest
    tampered['artifact_id'] = f'dixon_coles_regularized-{digest[:16]}'
    invalid = project_fixture(tampered, home_team_id='A', away_team_id='B', season='2425')
    assert invalid.status == 'invalid_model'
    assert invalid.distribution is None
    assert invalid.reason_codes == ('RHO_INVALID_FOR_FIXTURE',)


def test_projection_rho_is_valid_for_fixture(fitted):
    _, _, _, artifact = fitted
    projection = project_fixture(artifact, home_team_id='A', away_team_id='C', season='2425')
    lower, upper = rho_bounds(projection.lambda_home, projection.lambda_away)
    assert lower <= projection.rho <= upper


def test_baseline_artifact_uses_same_inference_entrypoint(fitted):
    matches, cutoff, _, _ = fitted
    baseline = build_ratio_baseline_artifact(matches, cutoff_utc=cutoff, minimum_team_matches=1)
    validate_model_artifact(baseline)
    projection = project_fixture(baseline, home_team_id='A', away_team_id='B', season='2425')
    assert projection.status == 'projection_ready_unvalidated'
    assert projection.rho == 0


@pytest.mark.parametrize('config', [
    FitConfig(half_life_days=120, minimum_matches=1),
    FitConfig(strength_l2=0, minimum_matches=1),
    FitConfig(minimum_matches=0),
])
def test_invalid_fit_config_is_rejected(config):
    matches = synthetic_matches()
    cutoff = max(match.result_available_at_utc for match in matches)
    with pytest.raises(ContractError):
        fit_dixon_coles(matches, cutoff_utc=cutoff, config=config)
