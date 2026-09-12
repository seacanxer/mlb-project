"""Transparent moment-based benchmark. Not the final fitted model."""
from collections import defaultdict

from .contracts import ContractError, require
from .data import matches_as_of


def fit_ratio_baseline(matches, *, cutoff_utc, minimum_team_matches=1):
    final = list(matches_as_of(matches, cutoff_utc))
    require(final, 'No final matches')
    avg_home = sum(m.home_goals for m in final) / len(final)
    avg_away = sum(m.away_goals for m in final) / len(final)
    require(avg_home > 0 and avg_away > 0, 'League goal average must be positive')
    stats = defaultdict(lambda: {'home_n': 0, 'away_n': 0, 'home_for': 0, 'home_against': 0,
                                 'away_for': 0, 'away_against': 0})
    for m in final:
        home, away = stats[m.home_team_id], stats[m.away_team_id]
        home['home_n'] += 1; home['home_for'] += m.home_goals; home['home_against'] += m.away_goals
        away['away_n'] += 1; away['away_for'] += m.away_goals; away['away_against'] += m.home_goals
    strengths = {}
    for team, s in stats.items():
        if s['home_n'] >= minimum_team_matches and s['away_n'] >= minimum_team_matches:
            strengths[team] = {
                'attack_home': s['home_for'] / s['home_n'] / avg_home,
                'defence_home': s['home_against'] / s['home_n'] / avg_away,
                'attack_away': s['away_for'] / s['away_n'] / avg_away,
                'defence_away': s['away_against'] / s['away_n'] / avg_home,
            }
    return {'avg_home_goals': avg_home, 'avg_away_goals': avg_away,
            'strengths': strengths, 'model': 'ratio-baseline-not-approved'}


def estimate_ratio_lambdas(home_team_id, away_team_id, model):
    try:
        home = model['strengths'][home_team_id]
        away = model['strengths'][away_team_id]
    except KeyError as exc:
        raise ContractError('Team lacks home/away baseline coverage') from exc
    lambda_home = home['attack_home'] * away['defence_away'] * model['avg_home_goals']
    lambda_away = away['attack_away'] * home['defence_home'] * model['avg_away_goals']
    require(lambda_home > 0 and lambda_away > 0, 'Baseline lambda must be positive')
    return lambda_home, lambda_away
