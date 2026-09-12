from pathlib import Path
import copy
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
from football_formula_engine.calibration import (
    calibrate_distribution, fit_coherent_tilt, identity_calibration,
    validate_calibration_artifact,
)
from football_formula_engine.contracts import ContractError
from football_formula_engine.metrics import binary_log_loss, evaluate_prediction_records, reliability_bins
from football_formula_engine.score_matrix import build_score_matrix


def test_identity_calibration_preserves_every_cell():
    distribution = build_score_matrix(1.6, 1.1, -0.08)
    calibrated = calibrate_distribution(distribution, identity_calibration())
    assert calibrated.probabilities == distribution.probabilities
    assert calibrated.lambda_home == distribution.lambda_home
    assert sum(probability for _, _, probability in calibrated.cells()) == pytest.approx(1)


def test_coherent_tilt_is_fitted_and_keeps_one_normalized_matrix():
    distributions = [build_score_matrix(1.7, 1.3, -0.05) for _ in range(12)]
    outcomes = [(0, 0), (1, 0), (0, 1), (1, 1)] * 3
    artifact = fit_coherent_tilt(distributions, outcomes, l2=1.0)
    validate_calibration_artifact(artifact)
    assert artifact['method'] == 'coherent_exponential_tilt'
    assert any(abs(value) > 1e-8 for value in artifact['coefficients'])
    calibrated = calibrate_distribution(distributions[0], artifact)
    assert sum(probability for _, _, probability in calibrated.cells()) == pytest.approx(1)
    assert calibrated.probabilities != distributions[0].probabilities
    assert calibrated.tail_mass_bound >= distributions[0].tail_mass_bound


def test_calibration_hash_tampering_is_rejected():
    artifact = copy.deepcopy(identity_calibration())
    artifact['coefficients'][0] = 1
    with pytest.raises(ContractError, match='hash mismatch'):
        validate_calibration_artifact(artifact)


def test_binary_metrics_and_reliability_boundaries():
    assert binary_log_loss(0.8, 1) == pytest.approx(-__import__('math').log(0.8))
    bins = reliability_bins([(0.0, 0), (0.1, 1), (1.0, 1)], count=10)
    assert bins[0]['count'] == 1
    assert bins[1]['count'] == 1
    assert bins[9]['count'] == 1


def test_metric_report_uses_correct_under_25_boundary():
    records = [{
        'actual_home': 1, 'actual_away': 1, 'score_probability': 0.1,
        'probabilities': {'1x2': {'home': 0.4, 'draw': 0.3, 'away': 0.3},
                          'btts_yes': 0.6, 'ou25_over': 0.7},
        'tail_mass_bound': 1e-9,
    }]
    report = evaluate_prediction_records(records)
    # A 1-1 result is Under 2.5, therefore an Over probability of .7 has Brier .49.
    assert report['ou25_brier'] == pytest.approx(0.49)
    assert report['btts_brier'] == pytest.approx(0.16)
