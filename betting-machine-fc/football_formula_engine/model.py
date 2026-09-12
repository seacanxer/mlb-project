"""Regularized, time-weighted Dixon-Coles fitting and versioned model artifacts.

Artifacts produced here are deliberately unvalidated and never official.  The
same ``project_fixture`` function is used by replay/offline and future live
adapters so the inference mathematics cannot silently diverge.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

from .baseline import estimate_ratio_lambdas, fit_ratio_baseline
from .contracts import ContractError, require
from .data import matches_as_of
from .score_matrix import build_score_matrix, rho_bounds


ARTIFACT_SCHEMA = 'fc-model-artifact-v1'
FORMULA_VERSION = 'dc-loglink-time-decay-v1'
BASELINE_VERSION = 'ratio-baseline-v1'
REGISTERED_HALF_LIVES = (90, 180, 365)


@dataclass(frozen=True)
class FitConfig:
    half_life_days: int = 180
    strength_l2: float = 1.0
    season_l2: float = 0.25
    rho_l2: float = 10.0
    minimum_matches: int = 40
    minimum_team_matches: int = 6
    max_iterations: int = 1000
    tolerance: float = 1e-9
    seed: int = 0


@dataclass(frozen=True)
class FixtureProjection:
    status: str
    model_family: str
    formula_version: str
    lambda_home: float | None
    lambda_away: float | None
    rho: float | None
    reason_codes: tuple[str, ...]
    distribution: object | None


def _canonical_bytes(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (TypeError, ValueError) as exc:
        raise ContractError('Model artifact is not canonical JSON') from exc


def _rounded(value):
    if isinstance(value, float):
        require(math.isfinite(value), 'Nonfinite artifact value')
        return round(value, 12)
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_rounded(item) for item in value]
    return value


def training_data_hash(matches):
    ordered = sorted((asdict(match) for match in matches), key=lambda row: row['fixture_id'])
    return hashlib.sha256(_canonical_bytes(ordered)).hexdigest()


def _seal_artifact(content):
    content = _rounded(content)
    digest = hashlib.sha256(_canonical_bytes(content)).hexdigest()
    return {'artifact_id': f"{content['model_family']}-{digest[:16]}",
            'content_sha256': digest, **content}


def validate_model_artifact(artifact):
    require(type(artifact) is dict, 'Model artifact must be an object')
    required = {'artifact_id', 'content_sha256', 'schema_version', 'model_family',
                'formula_version', 'validation_status', 'official_eligible', 'training',
                'config', 'parameters', 'diagnostics'}
    require(set(artifact) == required, 'Invalid model artifact fields')
    require(artifact['schema_version'] == ARTIFACT_SCHEMA, 'Unknown model artifact schema')
    require(artifact['model_family'] in ('dixon_coles_regularized', 'ratio_baseline'),
            'Unknown model family')
    require(type(artifact['artifact_id']) is str and bool(artifact['artifact_id']), 'Invalid artifact ID')
    require(type(artifact['content_sha256']) is str
            and re.fullmatch(r'[a-f0-9]{64}', artifact['content_sha256']) is not None,
            'Invalid artifact content hash')
    require(artifact['validation_status'] == 'unvalidated', 'Phase 4 artifact cannot be approved')
    require(artifact['official_eligible'] is False, 'Phase 4 artifact cannot be official')
    content = {key: value for key, value in artifact.items()
               if key not in ('artifact_id', 'content_sha256')}
    digest = hashlib.sha256(_canonical_bytes(content)).hexdigest()
    require(artifact['content_sha256'] == digest, 'Model artifact hash mismatch')
    require(artifact['artifact_id'] == f"{artifact['model_family']}-{digest[:16]}",
            'Model artifact ID mismatch')
    training = artifact['training']
    require(type(training) is dict and type(training.get('cutoff_utc')) is int
            and type(training.get('cutoff_utc')) is not bool and training['cutoff_utc'] >= 0,
            'Invalid training metadata')
    require(type(training.get('data_hash')) is str
            and re.fullmatch(r'[a-f0-9]{64}', training['data_hash']) is not None,
            'Invalid training hash')
    require(type(training.get('competition_id')) is str and bool(training['competition_id']),
            'Invalid training competition')
    require(type(training.get('seasons')) is list and bool(training['seasons'])
            and all(type(value) is str and bool(value) for value in training['seasons']),
            'Invalid training seasons')
    require(type(training.get('used_match_count')) is int
            and type(training['used_match_count']) is not bool and training['used_match_count'] > 0,
            'Invalid training match count')
    require(training.get('result_availability_enforced') is True,
            'Result availability gate not recorded')
    require(type(artifact['config']) is dict and type(artifact['parameters']) is dict
            and type(artifact['diagnostics']) is dict, 'Invalid artifact sections')

    def finite(value):
        return type(value) in (int, float) and type(value) is not bool and math.isfinite(value)

    if artifact['model_family'] == 'dixon_coles_regularized':
        require(artifact['formula_version'] == FORMULA_VERSION, 'Unexpected DC formula version')
        require(artifact['config'].get('half_life_days') in REGISTERED_HALF_LIVES,
                'Unregistered artifact half-life')
        require(type(artifact['config'].get('minimum_team_matches')) is int
                and artifact['config']['minimum_team_matches'] > 0, 'Invalid team coverage threshold')
        parameters = artifact['parameters']
        require(set(parameters) == {'season_effects', 'team_effects', 'rho', 'unseen_team_effect'},
                'Invalid DC parameters')
        require(finite(parameters['rho']), 'Invalid rho parameter')
        require(type(parameters['season_effects']) is dict and parameters['season_effects'],
                'Missing season effects')
        require(set(parameters['season_effects']) == set(training['seasons']),
                'Season parameter mismatch')
        for effect in parameters['season_effects'].values():
            require(type(effect) is dict and set(effect) == {'log_base_rate', 'home_advantage'}
                    and all(finite(value) for value in effect.values()), 'Invalid season effect')
        require(type(parameters['team_effects']) is dict and len(parameters['team_effects']) >= 2,
                'Missing team effects')
        for effect in parameters['team_effects'].values():
            require(type(effect) is dict
                    and set(effect) == {'attack', 'defence_vulnerability', 'training_matches'}
                    and finite(effect['attack']) and finite(effect['defence_vulnerability'])
                    and type(effect['training_matches']) is int and effect['training_matches'] >= 0,
                    'Invalid team effect')
        require(abs(sum(effect['attack'] for effect in parameters['team_effects'].values())) <= 1e-8,
                'Attack effects violate identifiability')
        require(abs(sum(effect['defence_vulnerability'] for effect in parameters['team_effects'].values())) <= 1e-8,
                'Defence effects violate identifiability')
        require(parameters['unseen_team_effect'] == {
            'attack': 0.0, 'defence_vulnerability': 0.0,
            'status': 'projection_only_out_of_domain'}, 'Invalid unseen-team prior')
    else:
        require(artifact['formula_version'] == BASELINE_VERSION, 'Unexpected baseline formula version')
        parameters = artifact['parameters']
        require(parameters.get('model') == 'ratio-baseline-not-approved', 'Invalid baseline marker')
        require(finite(parameters.get('avg_home_goals')) and parameters['avg_home_goals'] > 0
                and finite(parameters.get('avg_away_goals')) and parameters['avg_away_goals'] > 0,
                'Invalid baseline rates')
        require(type(parameters.get('strengths')) is dict, 'Invalid baseline strengths')
    return artifact


def _validate_config(config):
    require(type(config.half_life_days) is int and config.half_life_days in REGISTERED_HALF_LIVES,
            'Half-life must be a registered Phase 4 candidate')
    for value in (config.strength_l2, config.season_l2, config.rho_l2, config.tolerance):
        require(type(value) in (int, float) and type(value) is not bool and math.isfinite(value) and value > 0,
                'Fit penalties/tolerance must be positive finite numbers')
    for value in (config.minimum_matches, config.minimum_team_matches, config.max_iterations):
        require(type(value) is int and type(value) is not bool and value > 0,
                'Fit limits must be positive integers')
    require(type(config.seed) is int and type(config.seed) is not bool, 'Seed must be an integer')


def _fit_config_dict(config):
    value = asdict(config)
    value['registered_half_life_days'] = list(REGISTERED_HALF_LIVES)
    value['half_life_selection_status'] = 'deferred_to_phase_5_inner_validation'
    return value


def _rho_from_raw(raw, lower, upper):
    # The fixture-dependent DC positivity interval is respected during fitting.
    # A small margin keeps the likelihood away from a zero tau boundary.
    scaled = 0.98 * math.tanh(float(raw))
    return scaled * (upper if scaled >= 0 else -lower)


def _prepare_training(matches, cutoff_utc, config, neutral_fixture_ids):
    require(type(cutoff_utc) is int and type(cutoff_utc) is not bool, 'Cutoff must be UTC seconds')
    final = sorted(matches_as_of(matches, cutoff_utc), key=lambda match: (match.kickoff_utc, match.fixture_id))
    require(len(final) >= config.minimum_matches, 'Insufficient final matches at cutoff')
    competitions = {match.competition_id for match in final}
    require(len(competitions) == 1, 'Fit one competition per artifact')
    require(all(match.home_goals is not None and match.away_goals is not None for match in final),
            'Training result is incomplete')
    require(all(match.result_available_at_utc is not None and match.result_available_at_utc <= cutoff_utc
                for match in final), 'Training set violates result availability cutoff')
    neutral_fixture_ids = frozenset(neutral_fixture_ids or ())
    fixture_ids = {match.fixture_id for match in final}
    require(neutral_fixture_ids <= fixture_ids, 'Neutral fixture is outside the cutoff training set')
    return final, next(iter(competitions)), neutral_fixture_ids


def fit_dixon_coles(matches, *, cutoff_utc, config=FitConfig(), neutral_fixture_ids=None):
    """Fit one competition with season intercepts and sum-to-zero team effects."""
    _validate_config(config)
    source_matches = tuple(matches)
    final, competition_id, neutral_fixture_ids = _prepare_training(
        source_matches, cutoff_utc, config, neutral_fixture_ids)
    teams = sorted({match.home_team_id for match in final} | {match.away_team_id for match in final})
    seasons = sorted({match.season for match in final})
    require(len(teams) >= 2, 'At least two teams are required')
    team_index = {team: index for index, team in enumerate(teams)}
    season_index = {season: index for index, season in enumerate(seasons)}
    home_index = np.asarray([team_index[m.home_team_id] for m in final], dtype=np.int64)
    away_index = np.asarray([team_index[m.away_team_id] for m in final], dtype=np.int64)
    season_values = np.asarray([season_index[m.season] for m in final], dtype=np.int64)
    home_goals = np.asarray([m.home_goals for m in final], dtype=np.float64)
    away_goals = np.asarray([m.away_goals for m in final], dtype=np.float64)
    home_indicator = np.asarray([0.0 if m.fixture_id in neutral_fixture_ids else 1.0 for m in final])

    raw_weights = np.asarray([
        math.exp(-math.log(2) * max(0, cutoff_utc - m.result_available_at_utc)
                 / (86400 * config.half_life_days)) for m in final
    ], dtype=np.float64)
    weights = raw_weights * (len(final) / float(raw_weights.sum()))
    effective_matches = float(weights.sum() ** 2 / np.square(weights).sum())

    base_priors, home_priors = [], []
    for season in seasons:
        mask = np.asarray([m.season == season for m in final])
        mean_home = float(home_goals[mask].mean())
        mean_away = float(away_goals[mask].mean())
        require(mean_home > 0 and mean_away > 0, 'Season goal mean must be positive')
        base_priors.append(math.log(mean_away))
        home_priors.append(math.log(mean_home / mean_away))
    base_priors = np.asarray(base_priors)
    home_priors = np.asarray(home_priors)

    season_count, team_count = len(seasons), len(teams)
    attack_start = season_count * 2
    defence_start = attack_start + team_count
    rho_position = defence_start + team_count
    weighted_games = (np.bincount(home_index, weights=weights, minlength=team_count)
                      + np.bincount(away_index, weights=weights, minlength=team_count))
    weighted_for = (np.bincount(home_index, weights=weights * home_goals, minlength=team_count)
                    + np.bincount(away_index, weights=weights * away_goals, minlength=team_count))
    weighted_against = (np.bincount(home_index, weights=weights * away_goals, minlength=team_count)
                        + np.bincount(away_index, weights=weights * home_goals, minlength=team_count))
    league_rate = float((weighted_for.sum() / weighted_games.sum()))
    prior_games = 5.0
    attack_initial = np.log((weighted_for + prior_games * league_rate)
                            / (weighted_games + prior_games) / league_rate)
    defence_initial = np.log((weighted_against + prior_games * league_rate)
                             / (weighted_games + prior_games) / league_rate)
    attack_initial -= attack_initial.mean()
    defence_initial -= defence_initial.mean()
    initial = np.concatenate((base_priors, home_priors,
                              attack_initial, defence_initial, np.zeros(1)))

    def unpack(vector):
        base = vector[:season_count]
        home_advantage = vector[season_count:attack_start]
        # Centering every evaluation enforces the constraints without making one
        # arbitrarily chosen team's effect the negative sum of all free effects.
        # That reference-team parameterization can create a badly scaled search
        # direction in leagues with many teams.
        attack_raw = vector[attack_start:defence_start]
        defence_raw = vector[defence_start:rho_position]
        attack = attack_raw - attack_raw.mean()
        defence = defence_raw - defence_raw.mean()
        return base, home_advantage, attack, defence, vector[rho_position]

    def objective(vector):
        base, home_advantage, attack, defence, rho_raw = unpack(vector)
        log_home = base[season_values] + home_advantage[season_values] * home_indicator \
            + attack[home_index] + defence[away_index]
        log_away = base[season_values] + attack[away_index] + defence[home_index]
        if np.any(log_home < -6) or np.any(log_home > 5) or np.any(log_away < -6) or np.any(log_away > 5):
            return 1e50 + float(np.square(vector).sum())
        lambda_home, lambda_away = np.exp(log_home), np.exp(log_away)
        lower = float(np.maximum(-1 / lambda_home, -1 / lambda_away).max())
        upper = float(np.minimum(1.0, 1 / (lambda_home * lambda_away)).min())
        if not lower < upper:
            return 1e50
        rho = _rho_from_raw(rho_raw, lower, upper)
        tau = np.ones(len(final))
        tau[(home_goals == 0) & (away_goals == 0)] = 1 - lambda_home[(home_goals == 0) & (away_goals == 0)] * lambda_away[(home_goals == 0) & (away_goals == 0)] * rho
        tau[(home_goals == 1) & (away_goals == 0)] = 1 + lambda_away[(home_goals == 1) & (away_goals == 0)] * rho
        tau[(home_goals == 0) & (away_goals == 1)] = 1 + lambda_home[(home_goals == 0) & (away_goals == 1)] * rho
        tau[(home_goals == 1) & (away_goals == 1)] = 1 - rho
        if np.any(tau <= 0) or not np.all(np.isfinite(tau)):
            return 1e50
        log_likelihood = (home_goals * log_home - lambda_home - gammaln(home_goals + 1)
                          + away_goals * log_away - lambda_away - gammaln(away_goals + 1)
                          + np.log(tau))
        penalty = (0.5 * config.strength_l2 * (np.square(attack).sum() + np.square(defence).sum())
                   + 0.5 * config.season_l2 * (np.square(base - base_priors).sum()
                                               + np.square(home_advantage - home_priors).sum())
                   + 0.5 * config.rho_l2 * rho * rho)
        result = -float(np.dot(weights, log_likelihood)) + float(penalty)
        return result if math.isfinite(result) else 1e50

    bounds = ([(-3.0, 2.0)] * season_count + [(-1.5, 1.5)] * season_count
              + [(-2.0, 2.0)] * (team_count * 2) + [(-3.0, 3.0)])
    fitted = minimize(objective, initial, method='SLSQP', jac='3-point', bounds=bounds,
                      options={'maxiter': config.max_iterations, 'ftol': config.tolerance,
                               'finite_diff_rel_step': 1e-4})
    require(bool(fitted.success) and math.isfinite(float(fitted.fun)),
            f'Model fit did not converge: {fitted.message}')
    base, home_advantage, attack, defence, rho_raw = unpack(fitted.x)
    fitted_home = np.exp(base[season_values] + home_advantage[season_values] * home_indicator
                         + attack[home_index] + defence[away_index])
    fitted_away = np.exp(base[season_values] + attack[away_index] + defence[home_index])
    lower = float(np.maximum(-1 / fitted_home, -1 / fitted_away).max())
    upper = float(np.minimum(1.0, 1 / (fitted_home * fitted_away)).min())
    rho = _rho_from_raw(rho_raw, lower, upper)
    appearances = {team: 0 for team in teams}
    for match in final:
        appearances[match.home_team_id] += 1
        appearances[match.away_team_id] += 1

    content = {
        'schema_version': ARTIFACT_SCHEMA,
        'model_family': 'dixon_coles_regularized',
        'formula_version': FORMULA_VERSION,
        'validation_status': 'unvalidated',
        'official_eligible': False,
        'training': {
            'competition_id': competition_id,
            'seasons': seasons,
            'cutoff_utc': cutoff_utc,
            'data_hash': training_data_hash(final),
            'used_match_count': len(final),
            'result_availability_enforced': True,
        },
        'config': _fit_config_dict(config),
        'parameters': {
            'season_effects': {season: {'log_base_rate': float(base[index]),
                                        'home_advantage': float(home_advantage[index])}
                               for index, season in enumerate(seasons)},
            'team_effects': {team: {'attack': float(attack[index]),
                                    'defence_vulnerability': float(defence[index]),
                                    'training_matches': appearances[team]}
                             for index, team in enumerate(teams)},
            'rho': float(rho),
            'unseen_team_effect': {'attack': 0.0, 'defence_vulnerability': 0.0,
                                   'status': 'projection_only_out_of_domain'},
        },
        'diagnostics': {
            'optimizer': 'scipy-SLSQP',
            'converged': True,
            'optimizer_message': str(fitted.message),
            'iterations': int(fitted.nit),
            'objective': float(fitted.fun),
            'effective_match_count': effective_matches,
            'oldest_weight_relative_to_newest': float(raw_weights.min() / raw_weights.max()),
            'neutral_fixture_count': len(neutral_fixture_ids),
            'rho_training_lower_bound': lower,
            'rho_training_upper_bound': upper,
            'lambda_home_min': float(fitted_home.min()),
            'lambda_home_max': float(fitted_home.max()),
            'lambda_away_min': float(fitted_away.min()),
            'lambda_away_max': float(fitted_away.max()),
            'attack_sum': float(attack.sum()),
            'defence_vulnerability_sum': float(defence.sum()),
            'low_coverage_teams': sorted(team for team, count in appearances.items()
                                         if count < config.minimum_team_matches),
            'seed_usage': 'recorded_no_stochastic_initialization',
            'validation_note': 'Phase 5 chronological evaluation required; no ROI claim',
        },
    }
    return _seal_artifact(content)


def build_ratio_baseline_artifact(matches, *, cutoff_utc, minimum_team_matches=1):
    source_matches = tuple(matches)
    final = tuple(matches_as_of(source_matches, cutoff_utc))
    require(final, 'No final matches at cutoff')
    competitions = {match.competition_id for match in final}
    require(len(competitions) == 1, 'Build one competition baseline per artifact')
    model = fit_ratio_baseline(final, cutoff_utc=cutoff_utc,
                               minimum_team_matches=minimum_team_matches)
    content = {
        'schema_version': ARTIFACT_SCHEMA,
        'model_family': 'ratio_baseline',
        'formula_version': BASELINE_VERSION,
        'validation_status': 'unvalidated',
        'official_eligible': False,
        'training': {'competition_id': next(iter(competitions)),
                     'seasons': sorted({match.season for match in final}),
                     'cutoff_utc': cutoff_utc, 'data_hash': training_data_hash(final),
                     'used_match_count': len(final),
                     'result_availability_enforced': True},
        'config': {'minimum_team_matches': minimum_team_matches},
        'parameters': model,
        'diagnostics': {'validation_note': 'Benchmark only; Phase 5 evaluation required; no ROI claim'},
    }
    return _seal_artifact(content)


def project_fixture(artifact, *, home_team_id, away_team_id, season, neutral=False,
                    tail_tolerance=1e-8):
    """The sole artifact-to-distribution inference path for offline and live callers."""
    validate_model_artifact(artifact)
    require(type(home_team_id) is str and bool(home_team_id), 'Invalid home team ID')
    require(type(away_team_id) is str and bool(away_team_id), 'Invalid away team ID')
    require(home_team_id != away_team_id, 'Teams must differ')
    require(type(season) is str and bool(season), 'Invalid season')
    require(type(neutral) is bool, 'Neutral flag must be boolean')
    family = artifact['model_family']
    reasons = []
    if family == 'ratio_baseline':
        try:
            lambda_home, lambda_away = estimate_ratio_lambdas(
                home_team_id, away_team_id, artifact['parameters'])
        except ContractError:
            return FixtureProjection('projection_blocked', family, artifact['formula_version'],
                                     None, None, None, ('TEAM_COVERAGE_MISSING',), None)
        rho = 0.0
    else:
        effects = artifact['parameters']['season_effects']
        if season not in effects:
            return FixtureProjection('projection_blocked', family, artifact['formula_version'],
                                     None, None, None, ('SEASON_OUT_OF_DOMAIN',), None)
        team_effects = artifact['parameters']['team_effects']
        unseen = artifact['parameters']['unseen_team_effect']
        home = team_effects.get(home_team_id, unseen)
        away = team_effects.get(away_team_id, unseen)
        if home_team_id not in team_effects:
            reasons.append('HOME_TEAM_OUT_OF_DOMAIN')
        if away_team_id not in team_effects:
            reasons.append('AWAY_TEAM_OUT_OF_DOMAIN')
        minimum = artifact['config']['minimum_team_matches']
        if home_team_id in team_effects and home['training_matches'] < minimum:
            reasons.append('HOME_TEAM_LOW_COVERAGE')
        if away_team_id in team_effects and away['training_matches'] < minimum:
            reasons.append('AWAY_TEAM_LOW_COVERAGE')
        season_effect = effects[season]
        log_home = (season_effect['log_base_rate']
                    + (0.0 if neutral else season_effect['home_advantage'])
                    + home['attack'] + away['defence_vulnerability'])
        log_away = (season_effect['log_base_rate']
                    + away['attack'] + home['defence_vulnerability'])
        lambda_home, lambda_away = math.exp(log_home), math.exp(log_away)
        rho = artifact['parameters']['rho']
    lower, upper = rho_bounds(lambda_home, lambda_away)
    if not lower <= rho <= upper:
        return FixtureProjection('invalid_model', family, artifact['formula_version'],
                                 lambda_home, lambda_away, rho,
                                 tuple(reasons + ['RHO_INVALID_FOR_FIXTURE']), None)
    try:
        distribution = build_score_matrix(lambda_home, lambda_away, rho,
                                          tail_tolerance=tail_tolerance)
    except ContractError:
        return FixtureProjection('invalid_model', family, artifact['formula_version'],
                                 lambda_home, lambda_away, rho,
                                 tuple(reasons + ['SCORE_MATRIX_INVALID']), None)
    status = 'projection_only_out_of_domain' if reasons else 'projection_ready_unvalidated'
    return FixtureProjection(status, family, artifact['formula_version'], lambda_home,
                             lambda_away, rho, tuple(reasons), distribution)
