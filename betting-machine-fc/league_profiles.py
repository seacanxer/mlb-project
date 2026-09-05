"""League/tier priors and production routing for Formula v4.

These values are descriptive scoring-environment priors from the research
report.  They are intentionally weak: a league average is never sufficient to
publish an Official Pick.  Full team ratings are still required for production.
"""
from dataclasses import dataclass

from strength_rating import norm, resolve_code


@dataclass(frozen=True)
class LeagueProfile:
    key: str
    baseline_total: float | None
    prior_weight: float
    data_grade: str
    route: str
    reason: str


_EXACT = {
    "germany 3 liga": LeagueProfile("DE3", 2.854, 0.08, "B", "shadow", "two audited completed seasons"),
    "norway eliteserien": LeagueProfile("NO1", 3.043, 0.12, "B", "shadow", "dynamic calendar-league regime"),
    "norway 1 division": LeagueProfile("NO2", 3.056, 0.08, "B", "shadow", "2024 scoring change point"),
    "norway obos ligaen": LeagueProfile("NO2", 3.056, 0.08, "B", "shadow", "2024 scoring change point"),
    "iceland besta deild": LeagueProfile("IS1", 3.445, 0.12, "B", "shadow", "phase split requires calibration"),
    "iceland urvalsdeild": LeagueProfile("IS1", 3.445, 0.12, "B", "shadow", "phase split requires calibration"),
    "poland ekstraklasa": LeagueProfile("PL1", 2.727, 0.12, "B", "shadow", "stable league prior; odds audit pending"),
    "poland championship liga 1": LeagueProfile("PL2", 2.664, 0.06, "C", "shadow", "incomplete multi-season price history"),
    "sweden allsvenskan": LeagueProfile("SE1", 2.817, 0.12, "B", "shadow", "team ratings and prices pending"),
    "sweden superettan": LeagueProfile("SE2", 2.768, 0.08, "B", "shadow", "volatile season intercept"),
    "sweden division 1 north": LeagueProfile("SE3N", 3.169, 0.06, "C", "shadow", "group-specific prior"),
    "sweden ettan norra": LeagueProfile("SE3N", 3.169, 0.06, "C", "shadow", "group-specific prior"),
    "sweden division 1 south": LeagueProfile("SE3S", 2.800, 0.06, "C", "shadow", "group-specific prior"),
    "sweden ettan sodra": LeagueProfile("SE3S", 2.800, 0.06, "C", "shadow", "group-specific prior"),
}

_RATED_HISTORY_WEIGHTS = {
    "E0": 0.35, "E1": 0.30, "E2": 0.28, "E3": 0.25, "EC": 0.20,
    "D1": 0.40, "D2": 0.35,
    "SP1": 0.35, "SP2": 0.25,
    "SC0": 0.30, "SC1": 0.24, "SC2": 0.20, "SC3": 0.18,
    "N1": 0.35, "F1": 0.32, "F2": 0.28, "I1": 0.32, "I2": 0.28,
    "P1": 0.30, "B1": 0.30, "T1": 0.25, "G1": 0.22,
}

_BLOCKED_MARKERS = (
    " women", " woman", " u17", " u18", " u19", " u20", " u21", " u23",
    " youth", " reserve", " reserves", " cup", " friendly", " qualification",
)

_AMBIGUOUS_OR_UNVALIDATED = (
    "oberliga", "regionalliga", "iceland 1 deild", "iceland 2 deild",
    "iceland 3 deild", "poland championship liga 3", "poland championship liga 4",
    "spain primera division rfef", "spain segunda federation", "spain tercera federation",
    "sweden division 1", "sweden division 2", "sweden division 3", "sweden division 4",
    "norway division 2", "norway division 3",
)


def get_league_profile(label):
    normalized = norm(label)
    if not normalized:
        return LeagueProfile("UNKNOWN", None, 0.0, "D", "blocked", "missing league identity")
    if any(marker.strip() in normalized.split() for marker in ("women", "woman", "youth")):
        return LeagueProfile("NON_SENIOR", None, 0.0, "D", "blocked", "non-senior competition")
    if any(marker in f" {normalized}" for marker in _BLOCKED_MARKERS):
        return LeagueProfile("NON_STANDARD", None, 0.0, "D", "blocked", "cup/youth/reserve competition")
    if normalized in _EXACT:
        return _EXACT[normalized]
    if any(marker in normalized for marker in _AMBIGUOUS_OR_UNVALIDATED):
        return LeagueProfile("UNVALIDATED", None, 0.0, "D", "blocked", "tier/group data is not validated")

    code = resolve_code(label)
    if code:
        return LeagueProfile(
            code, None, _RATED_HISTORY_WEIGHTS.get(code, 0.25),
            "A", "rated", "team-rating league",
        )
    return LeagueProfile("UNSUPPORTED", None, 0.0, "D", "blocked", "no validated league model")
