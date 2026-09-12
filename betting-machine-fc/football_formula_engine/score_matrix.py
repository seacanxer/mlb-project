"""Deterministic independent-Poisson/Dixon-Coles score distribution."""
from dataclasses import dataclass
import math

from .contracts import ContractError, number, require


@dataclass(frozen=True)
class ScoreDistribution:
    probabilities: tuple[tuple[float, ...], ...]
    lambda_home: float
    lambda_away: float
    rho: float
    max_goals: int
    raw_mass: float
    tail_mass_bound: float

    def cells(self):
        for home, row in enumerate(self.probabilities):
            for away, probability in enumerate(row):
                yield home, away, probability


def poisson_probabilities(rate, max_goals):
    values = [math.exp(-rate)]
    for goals in range(1, max_goals + 1):
        values.append(values[-1] * rate / goals)
    return values


def adaptive_max_goals(lambda_home, lambda_away, tolerance, hard_limit):
    home = away = 0.0
    home_p, away_p = math.exp(-lambda_home), math.exp(-lambda_away)
    for goals in range(hard_limit + 1):
        if goals:
            home_p *= lambda_home / goals
            away_p *= lambda_away / goals
        home += home_p; away += away_p
        if (1 - home) + (1 - away) <= tolerance:
            return max(goals, 1)
    raise ContractError('Tail tolerance not reached before hard limit')


def rho_bounds(lambda_home, lambda_away):
    return max(-1 / lambda_home, -1 / lambda_away), min(1.0, 1 / (lambda_home * lambda_away))


def dixon_coles_tau(home, away, lambda_home, lambda_away, rho):
    if (home, away) == (0, 0): return 1 - lambda_home * lambda_away * rho
    if (home, away) == (1, 0): return 1 + lambda_away * rho
    if (home, away) == (0, 1): return 1 + lambda_home * rho
    if (home, away) == (1, 1): return 1 - rho
    return 1.0


def build_score_matrix(lambda_home, lambda_away, rho=0.0, *, tail_tolerance=1e-8, hard_limit=200):
    for value in (lambda_home, lambda_away, rho, tail_tolerance): number(value)
    require(lambda_home > 0 and lambda_away > 0, 'Lambdas must be positive')
    require(0 < tail_tolerance < 1, 'Invalid tail tolerance')
    require(type(hard_limit) is int and 1 <= hard_limit <= 1000, 'Invalid hard limit')
    lower, upper = rho_bounds(lambda_home, lambda_away)
    require(lower <= rho <= upper, 'Rho makes Dixon-Coles mass negative')
    maximum = adaptive_max_goals(lambda_home, lambda_away, tail_tolerance, hard_limit)
    home_p = poisson_probabilities(lambda_home, maximum)
    away_p = poisson_probabilities(lambda_away, maximum)
    raw = []
    for home in range(maximum + 1):
        row = []
        for away in range(maximum + 1):
            value = home_p[home] * away_p[away] * dixon_coles_tau(home, away, lambda_home, lambda_away, rho)
            require(value >= 0 and math.isfinite(value), 'Invalid score probability')
            row.append(value)
        raw.append(row)
    raw_mass = sum(map(sum, raw))
    require(raw_mass > 0 and raw_mass <= 1 + 1e-12, 'Invalid score mass')
    tail_bound = max(0.0, (1 - sum(home_p)) + (1 - sum(away_p)))
    require(tail_bound <= tail_tolerance + 1e-14, 'Tail bound exceeded')
    normalized = tuple(tuple(value / raw_mass for value in row) for row in raw)
    return ScoreDistribution(normalized, lambda_home, lambda_away, rho, maximum, raw_mass, tail_bound)
