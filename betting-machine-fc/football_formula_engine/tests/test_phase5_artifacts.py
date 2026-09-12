import hashlib
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
from football_formula_engine.data import load_football_data_csv
from football_formula_engine.contracts import ContractError
from football_formula_engine.evaluation import (EVALUATION_SCHEMA, canonical_bytes,
                                                resolve_split, validate_sealed_artifact)
from football_formula_engine.uncertainty import moving_block_sample

PACKAGE = ROOT / 'betting-machine-fc' / 'football_formula_engine'
ARTIFACTS = PACKAGE / 'artifacts'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def load_matches(spec):
    values = []
    for source in spec['dataset']:
        matches, _ = load_football_data_csv(
            ROOT / source['path'], competition_id=spec['competition_id'],
            season=source['season'], timezone_name=spec['timezone'])
        values.extend(matches)
    return tuple(values)


def test_frozen_phase5_report_matches_spec_and_strict_chronology():
    spec = read_json(PACKAGE / 'evaluation_spec.json')
    registry = read_json(ARTIFACTS / 'phase5-validation-registry.json')
    report = read_json(ARTIFACTS / 'evaluations' / f"{registry['evaluation_id']}.json")
    assert report['evaluation_spec_sha256'] == hashlib.sha256(canonical_bytes(spec)).hexdigest()
    matches = load_matches(spec)
    previous_target_end = None
    for name in ('calibration', 'policy_validation', 'untouched_test'):
        cutoff, target = resolve_split(matches, spec['splits'][name])
        assert cutoff == report['split_summary'][name]['training_cutoff_utc']
        assert len(target) == report['split_summary'][name]['prediction_count']
        assert cutoff < min(match.kickoff_utc for match in target)
        if previous_target_end is not None:
            assert previous_target_end < min(match.kickoff_utc for match in target)
        previous_target_end = max(match.kickoff_utc for match in target)


def test_selection_used_policy_only_and_test_stays_unapproved():
    registry = read_json(ARTIFACTS / 'phase5-validation-registry.json')
    report = read_json(ARTIFACTS / 'evaluations' / f"{registry['evaluation_id']}.json")
    assert report['selection']['selected_on'] == 'policy_validation'
    assert report['selection']['half_life_days'] == 365
    assert report['selection']['calibration_method'] == 'identity'
    assert report['split_summary']['untouched_test']['prediction_count'] == 300
    assert report['validation_status'] == 'not_approved'
    assert report['quality_gate']['approved'] is False
    assert registry['official_enabled'] is False
    assert registry['runtime_activation'] == 'disabled'
    validate_sealed_artifact(report, kind='evaluation', schema_version=EVALUATION_SCHEMA)


def test_evaluation_hash_tampering_is_rejected():
    registry = read_json(ARTIFACTS / 'phase5-validation-registry.json')
    report = read_json(ARTIFACTS / 'evaluations' / f"{registry['evaluation_id']}.json")
    report['official_enabled'] = True
    with pytest.raises(ContractError, match='hash mismatch'):
        validate_sealed_artifact(report, kind='evaluation', schema_version=EVALUATION_SCHEMA)


def test_btts_and_ou_fail_against_league_average_without_roi_claim():
    registry = read_json(ARTIFACTS / 'phase5-validation-registry.json')
    report = read_json(ARTIFACTS / 'evaluations' / f"{registry['evaluation_id']}.json")
    selected = report['test_metrics']['selected_candidate']
    league = report['test_metrics']['league_average_poisson']
    assert selected['btts_brier'] > league['btts_brier']
    assert selected['ou25_brier'] > league['ou25_brier']
    assert report['roi_status'] == 'NOT_EVALUABLE_NO_TIMED_ENTRY_QUOTES'
    assert report['clv_status'] == 'NOT_EVALUABLE_NO_TIMED_MATCHED_QUOTES'
    assert registry['segment_status']['btts'] == 'not_approved'
    assert registry['segment_status']['ou_2_5'] == 'not_approved'


def test_bootstrap_checkpoints_and_uncertainty_are_explicitly_insufficient():
    registry = read_json(ARTIFACTS / 'phase5-validation-registry.json')
    uncertainty = read_json(ARTIFACTS / 'uncertainty' / f"{registry['uncertainty_id']}.json")
    checkpoints = list((ARTIFACTS / 'bootstrap-replicates').glob(
        f"{registry['evaluation_id']}-r*.json"))
    assert len(checkpoints) == uncertainty['successful_replicates'] == 8
    assert uncertainty['minimum_reliable_replicates'] == 30
    assert uncertainty['status'] == 'UNCERTAINTY_UNAVAILABLE_INSUFFICIENT_REPLICATES'
    assert uncertainty['official_eligible'] is False


def test_moving_block_sampling_is_deterministic_and_preserves_blocks():
    spec = read_json(PACKAGE / 'evaluation_spec.json')
    matches = load_matches(spec)[:100]
    first, starts = moving_block_sample(matches, block_length=20, seed=7)
    second, second_starts = moving_block_sample(matches, block_length=20, seed=7)
    assert [match.fixture_id for match in first] == [match.fixture_id for match in second]
    assert starts == second_starts
    assert len(first) == len(matches)
    assert first[:20] == tuple(sorted(matches, key=lambda match: (match.kickoff_utc, match.fixture_id)))[starts[0]:starts[0] + 20]
