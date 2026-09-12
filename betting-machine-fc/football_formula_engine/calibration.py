"""Coherent exponential-tilt calibration for score distributions."""
import hashlib
import json
import math
import re

import numpy as np
from scipy.optimize import minimize

from .contracts import ContractError, require
from .score_matrix import ScoreDistribution


CALIBRATION_SCHEMA = 'fc-calibration-artifact-v1'
FEATURES = ('total_le_2', 'home_win', 'draw', 'btts_yes')


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def _seal(content):
    digest = hashlib.sha256(_canonical(content)).hexdigest()
    return {'calibration_id': f"coherent-tilt-{digest[:16]}",
            'content_sha256': digest, **content}


def validate_calibration_artifact(artifact):
    require(type(artifact) is dict, 'Calibration artifact must be an object')
    required = {'calibration_id', 'content_sha256', 'schema_version', 'method',
                'features', 'coefficients', 'l2', 'training_prediction_count',
                'optimizer', 'validation_status', 'official_eligible'}
    require(set(artifact) == required, 'Invalid calibration artifact fields')
    require(artifact['schema_version'] == CALIBRATION_SCHEMA, 'Unknown calibration schema')
    require(artifact['method'] in ('identity', 'coherent_exponential_tilt'),
            'Unknown calibration method')
    require(artifact['features'] == list(FEATURES), 'Unexpected calibration features')
    require(type(artifact['coefficients']) is list and len(artifact['coefficients']) == len(FEATURES)
            and all(type(value) in (int, float) and type(value) is not bool and math.isfinite(value)
                    for value in artifact['coefficients']), 'Invalid calibration coefficients')
    require(type(artifact['l2']) in (int, float) and type(artifact['l2']) is not bool
            and math.isfinite(artifact['l2']) and artifact['l2'] >= 0, 'Invalid calibration penalty')
    require(type(artifact['training_prediction_count']) is int
            and artifact['training_prediction_count'] >= 0, 'Invalid calibration sample count')
    require(type(artifact['content_sha256']) is str
            and re.fullmatch(r'[a-f0-9]{64}', artifact['content_sha256']),
            'Invalid calibration hash')
    require(artifact['validation_status'] == 'unvalidated'
            and artifact['official_eligible'] is False, 'Calibration approval gate violated')
    content = {key: value for key, value in artifact.items()
               if key not in ('calibration_id', 'content_sha256')}
    digest = hashlib.sha256(_canonical(content)).hexdigest()
    require(digest == artifact['content_sha256'], 'Calibration hash mismatch')
    require(artifact['calibration_id'] == f'coherent-tilt-{digest[:16]}',
            'Calibration ID mismatch')
    return artifact


def _features(home_goals, away_goals):
    return (int(home_goals + away_goals <= 2), int(home_goals > away_goals),
            int(home_goals == away_goals), int(home_goals > 0 and away_goals > 0))


def identity_calibration():
    return _seal({
        'schema_version': CALIBRATION_SCHEMA,
        'method': 'identity',
        'features': list(FEATURES),
        'coefficients': [0.0] * len(FEATURES),
        'l2': 0.0,
        'training_prediction_count': 0,
        'optimizer': {'status': 'not_required', 'iterations': 0, 'objective': None},
        'validation_status': 'unvalidated',
        'official_eligible': False,
    })


def calibrate_distribution(distribution, calibration_artifact):
    validate_calibration_artifact(calibration_artifact)
    coefficients = np.asarray(calibration_artifact['coefficients'], dtype=np.float64)
    shifts = []
    for home, row in enumerate(distribution.probabilities):
        shifts.append([float(np.dot(coefficients, _features(home, away)))
                       for away in range(len(row))])
    maximum = max(map(max, shifts))
    weighted = []
    for home, row in enumerate(distribution.probabilities):
        weighted.append([probability * math.exp(shifts[home][away] - maximum)
                         for away, probability in enumerate(row)])
    normalizer = sum(map(sum, weighted))
    require(normalizer > 0 and math.isfinite(normalizer), 'Invalid calibration normalizer')
    probabilities = tuple(tuple(value / normalizer for value in row) for row in weighted)
    spread = maximum - min(map(min, shifts))
    tail_bound = min(1.0, distribution.tail_mass_bound * math.exp(spread))
    return ScoreDistribution(probabilities, distribution.lambda_home,
                             distribution.lambda_away, distribution.rho,
                             distribution.max_goals, 1.0, tail_bound)


def fit_coherent_tilt(distributions, outcomes, *, l2):
    distributions, outcomes = tuple(distributions), tuple(outcomes)
    require(len(distributions) == len(outcomes) and distributions,
            'Calibration distributions/outcomes mismatch')
    require(type(l2) in (int, float) and type(l2) is not bool
            and math.isfinite(l2) and l2 > 0, 'Calibration L2 must be positive')
    for distribution, outcome in zip(distributions, outcomes):
        require(type(outcome) is tuple and len(outcome) == 2
                and all(type(value) is int and value >= 0 for value in outcome),
                'Invalid calibration outcome')
        require(outcome[0] <= distribution.max_goals and outcome[1] <= distribution.max_goals,
                'Observed score is outside calibrated grid')

    def objective(coefficients):
        total = 0.0
        for distribution, (actual_home, actual_away) in zip(distributions, outcomes):
            shifts = []
            weighted_mass = 0.0
            actual_shift = float(np.dot(coefficients, _features(actual_home, actual_away)))
            for home, row in enumerate(distribution.probabilities):
                for away, probability in enumerate(row):
                    shift = float(np.dot(coefficients, _features(home, away)))
                    shifts.append(shift)
                    weighted_mass += probability * math.exp(shift)
            actual_probability = distribution.probabilities[actual_home][actual_away]
            if actual_probability <= 0 or weighted_mass <= 0 or not math.isfinite(weighted_mass):
                return 1e50
            total += -math.log(actual_probability) - actual_shift + math.log(weighted_mass)
        return total / len(distributions) + 0.5 * l2 * float(np.square(coefficients).sum())

    fitted = minimize(objective, np.zeros(len(FEATURES)), method='SLSQP',
                      bounds=[(-2.0, 2.0)] * len(FEATURES),
                      options={'maxiter': 500, 'ftol': 1e-10})
    require(bool(fitted.success) and math.isfinite(float(fitted.fun)),
            f'Calibration did not converge: {fitted.message}')
    coefficients = [round(float(value), 12) for value in fitted.x]
    return _seal({
        'schema_version': CALIBRATION_SCHEMA,
        'method': 'coherent_exponential_tilt',
        'features': list(FEATURES),
        'coefficients': coefficients,
        'l2': float(l2),
        'training_prediction_count': len(distributions),
        'optimizer': {'status': 'converged', 'iterations': int(fitted.nit),
                      'objective': round(float(fitted.fun), 12)},
        'validation_status': 'unvalidated',
        'official_eligible': False,
    })
