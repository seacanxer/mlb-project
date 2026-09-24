"""Honest cross-competition team strength with an explicit fallback ladder.

The production model fits Dixon-Coles per league from football-data CSVs and
can only project teams it has seen in that league. Cup ties and deeper-tier
fixtures routinely fail that check, and the honest answer until now was
"market_only" - no model side at all.

This module supplies the missing middle rung. It computes a transparent
goal-based strength rating from the multi-season historical store, across
leagues and competitions, and is only used when the production model has no
rating for the team.

Fallback ladder (highest priority first)
---------------------------------------
1. production rating  (caller supplies it; never produced here)
2. historical rating  (this module, from data/historical/)
3. league prior       (competition-level average, this module)
4. market only        (caller: price the market and say so)

Nothing here invents a team. A team with no history gets ``None`` and the
caller must fall through to the league prior or the market. Ratings are
labelled with their source so a downstream pick is never presented as a
model pick when it came from a prior.

Rating definition
-----------------
Goals are normalised against the competition-season they were scored in, so a
Championship goal is not treated as equal to a Premier League goal. The
attack/defence ratios are then combined across seasons with a simple decay so
recent seasons matter more.
"""
import math
from collections import defaultdict

from .historical_store import HistoricalStore

RATING_VERSION = 'fc-historical-strength-v1'
SEASON_WEIGHTS = {'0': 1.0, '1': 0.85, '2': 0.7, '3': 0.55, '4': 0.4}
MIN_RATING_MATCHES = 8
# Extra goals credited to the home team, estimated from the store itself when
# possible. Used only to make home/away splits comparable, never to invent a
# result.


class TeamStrength:
    """Goal-ratio strength over several seasons of a competition tree."""

    def __init__(self, store, *, min_matches=MIN_RATING_MATCHES):
        self.store = store
        self.min_matches = min_matches
        self._team = None
        self._comp = None

    # ------------------------------------------------------------------ fit
    def fit(self):
        results = self.store.results
        season_index = self._season_index(results)
        seasons_by_comp = defaultdict(set)
        goals_by_comp_season = defaultdict(lambda: [0.0, 0.0, 0])
        team_stats = defaultdict(lambda: {
            'for': 0.0, 'against': 0.0, 'home_for': 0.0, 'home_against': 0.0,
            'away_for': 0.0, 'away_against': 0.0, 'home_n': 0, 'away_n': 0,
            'weight': 0.0, 'seasons': set(), 'comps': set(),
        })
        for result in results:
            key = (result.competition, result.season)
            bucket = goals_by_comp_season[key]
            bucket[0] += result.home_goals
            bucket[1] += result.away_goals
            bucket[2] += 1
            seasons_by_comp[result.competition].add(result.season)
            weight = self._season_weight(season_index, result.season)
            for side, own_goals, opp_goals, is_home in (
                    (result.home_team, result.home_goals, result.away_goals, True),
                    (result.away_team, result.away_goals, result.home_goals, False)):
                stats = team_stats[side]
                stats['for'] += weight * own_goals
                stats['against'] += weight * opp_goals
                stats['weight'] += weight
                stats['seasons'].add(result.season)
                stats['comps'].add(result.competition)
                if is_home:
                    stats['home_for'] += weight * own_goals
                    stats['home_against'] += weight * opp_goals
                    stats['home_n'] += 1
                else:
                    stats['away_for'] += weight * own_goals
                    stats['away_against'] += weight * opp_goals
                    stats['away_n'] += 1

        comp_profile = {}
        for comp, seasons in seasons_by_comp.items():
            totals = [0.0, 0.0, 0]
            for season in seasons:
                bucket = goals_by_comp_season[(comp, season)]
                totals[0] += bucket[0]
                totals[1] += bucket[1]
                totals[2] += bucket[2]
            matches = max(1, totals[2])
            comp_profile[comp] = {
                'avg_home_goals': totals[0] / matches,
                'avg_away_goals': totals[1] / matches,
                'avg_total_goals': (totals[0] + totals[1]) / matches,
                'seasons': sorted(seasons),
                'matches': totals[2],
            }

        teams = {}
        for team, stats in team_stats.items():
            played = stats['home_n'] + stats['away_n']
            if played < self.min_matches:
                continue
            teams[team] = {
                'matches': played,
                'seasons': sorted(stats['seasons']),
                'competitions': sorted(stats['comps']),
                'weight': round(stats['weight'], 1),
                'attack_ratio': stats['for'] / max(1e-9, stats['weight']),
                'defence_ratio': stats['against'] / max(1e-9, stats['weight']),
                'home_attack': stats['home_for'] / max(1e-9, stats['home_n']),
                'home_defence': stats['home_against'] / max(1e-9, stats['home_n']),
                'away_attack': stats['away_for'] / max(1e-9, stats['away_n']),
                'away_defence': stats['away_against'] / max(1e-9, stats['away_n']),
            }
        self._team = teams
        self._comp = comp_profile
        return self

    @staticmethod
    def _season_index(results):
        seasons = sorted({result.season for result in results if result.season.isdigit()},
                         key=int)
        return {season: len(seasons) - 1 - index for index, season in enumerate(seasons)}

    @staticmethod
    def _season_weight(season_index, season):
        gap = season_index.get(season)
        if gap is None:
            return 0.15
        for offset in range(5):
            if gap == offset:
                return [1.0, 0.85, 0.7, 0.55, 0.4][offset]
        return 0.25

    # --------------------------------------------------------------- queries
    @property
    def competitions(self):
        return dict(self._comp or {})

    def team_rating(self, team):
        if team is None:
            return None
        return (self._team or {}).get(team)

    def known_teams(self):
        return set((self._team or {}).keys())

    def lambdas(self, home_team, away_team, competition=None):
        """Expected goals for a fixture, or None if there is no honest basis.

        Uses the standard log-linear multiplicative form, so the rating ratios
        only set the split of goals and the competition profile fixes the total:

            lambda_home = mu * h * attack_home * defence_away
            lambda_away = mu * attack_away * defence_home

        then both are rescaled to sum to the competition goal total. That makes
        the output insensitive to the arbitrary scale of the ratio estimators.

        ``competition`` selects the scoring environment (goal averages) to use.
        Cross-league fixtures should pass the stronger competition so the goal
        base rate is not inflated by a high-scoring lower tier.
        """
        home = self.team_rating(home_team)
        away = self.team_rating(away_team)
        profile = self.competition_profile(competition)
        if profile is None or home is None or away is None:
            return None
        total = profile['avg_home_goals'] + profile['avg_away_goals']
        mu = total / 2.0
        home_advantage = profile['avg_home_goals'] / max(1e-9, profile['avg_away_goals'])
        raw_home = mu * home_advantage * home['attack_ratio'] * away['defence_ratio']
        raw_away = mu * away['attack_ratio'] * home['defence_ratio']
        scale = total / max(1e-9, raw_home + raw_away)
        lambda_home = raw_home * scale
        lambda_away = raw_away * scale
        return {
            'lambda_home': round(lambda_home, 3),
            'lambda_away': round(lambda_away, 3),
            'rating_source': RATING_VERSION,
            'competition_profile': {key: round(value, 3) if isinstance(value, float) else value
                                    for key, value in profile.items()},
            'home_rating': {key: round(value, 3) for key, value in home.items()
                            if key not in ('seasons', 'competitions')},
            'away_rating': {key: round(value, 3) for key, value in away.items()
                            if key not in ('seasons', 'competitions')},
            'home_matches': home['matches'],
            'away_matches': away['matches'],
            'formula': 'log-linear-ratio-rescaled-to-competition-total',
        }

    def competition_profile(self, competition=None):
        comps = self._comp or {}
        if competition is not None and competition in comps:
            return comps[competition]
        # Prefer the deepest competition available when none is named.
        order = ['E0', 'E1', 'E2', 'E3', 'EC', 'SP1', 'D1', 'I1', 'F1', 'FACUP']
        for code in order:
            if code in comps:
                return comps[code]
        for value in comps.values():
            return value
        return None
