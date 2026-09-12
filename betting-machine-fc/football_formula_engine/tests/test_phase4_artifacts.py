import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
from football_formula_engine.data import load_football_data_csv, matches_as_of
from football_formula_engine.model import training_data_hash, validate_model_artifact

PACKAGE = ROOT / 'betting-machine-fc' / 'football_formula_engine'
ARTIFACTS = PACKAGE / 'artifacts'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def test_phase4_registry_points_to_a_nontrivial_unvalidated_fit_and_baseline():
    registry = read_json(ARTIFACTS / 'phase4-model-registry.json')
    assert registry['runtime_activation'] == 'disabled'
    assert registry['official_enabled'] is False
    candidate = read_json(ARTIFACTS / 'models' / f"{registry['phase4_candidate_id']}.json")
    baseline = read_json(ARTIFACTS / 'models' / f"{registry['baseline_id']}.json")
    validate_model_artifact(candidate)
    validate_model_artifact(baseline)
    assert candidate['validation_status'] == baseline['validation_status'] == 'unvalidated'
    assert candidate['diagnostics']['iterations'] > 1
    assert any(abs(team['attack']) > 1e-6
               for team in candidate['parameters']['team_effects'].values())
    assert any(abs(team['defence_vulnerability']) > 1e-6
               for team in candidate['parameters']['team_effects'].values())


def test_phase4_artifact_hash_matches_frozen_cutoff_data():
    registry = read_json(ARTIFACTS / 'phase4-model-registry.json')
    candidate = read_json(ARTIFACTS / 'models' / f"{registry['phase4_candidate_id']}.json")
    cutoff = candidate['training']['cutoff_utc']
    matches = []
    for filename, season in (('E0_2425.csv', '2425'), ('E0_2526.csv', '2526')):
        normalized, _ = load_football_data_csv(
            ROOT / 'betting-machine-fc' / 'data' / filename,
            competition_id='E0', season=season, timezone_name='Europe/London')
        matches.extend(normalized)
    eligible = matches_as_of(matches, cutoff)
    assert len(eligible) == candidate['training']['used_match_count'] == 760
    assert training_data_hash(eligible) == candidate['training']['data_hash']


def test_rejected_diagnostic_artifact_is_not_selected():
    registry = read_json(ARTIFACTS / 'phase4-model-registry.json')
    rejected = [entry for entry in registry['entries'] if entry['status'] == 'rejected_engineering']
    assert rejected
    assert all(entry['artifact_id'] != registry['phase4_candidate_id'] for entry in rejected)
