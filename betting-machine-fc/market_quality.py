"""Shared payout semantics and quality policy for every football menu."""
import math

from model import RHO_DEFAULT, score_matrix, _sub_lines

POLICY_VERSION = "quality-v1"


def outcome_distribution(matrix, market, side, line):
    """Mutually exclusive full/half outcomes, plus expected stake fractions."""
    if market not in {"ou", "ah"} or side not in ({"over", "under"} if market == "ou" else {"home", "away"}):
        raise ValueError("unsupported market/side")
    if not math.isfinite(line) or abs(line * 4 - round(line * 4)) > 1e-8:
        raise ValueError("line must be a finite quarter-goal increment")
    result = dict.fromkeys(("full_win", "half_win", "push", "half_loss", "full_loss"), 0.0)
    for (home, away), probability in matrix.items():
        outcomes = []
        for leg in _sub_lines(line):
            delta = ((home + away - leg) * (1 if side == "over" else -1) if market == "ou"
                     else (home - away if side == "home" else away - home) + leg)
            outcomes.append(1 if delta > 1e-9 else (-1 if delta < -1e-9 else 0))
        name = {2: "full_win", 1: "half_win", 0: "push", -1: "half_loss", -2: "full_loss"}[sum(outcomes)]
        result[name] += probability
    result["win_fraction"] = result["full_win"] + result["half_win"] / 2
    result["loss_fraction"] = result["full_loss"] + result["half_loss"] / 2
    result["push_fraction"] = result["push"] + (result["half_win"] + result["half_loss"]) / 2
    result["profit_probability"] = result["full_win"] + result["half_win"]
    return result


def payout_metrics(market, side, line, odds, lh, la, rho=RHO_DEFAULT):
    matrix, _ = score_matrix(lh, la, rho)
    result = outcome_distribution(matrix, market, side, line)
    result["ev"] = result["win_fraction"] * (odds - 1) - result["loss_fraction"]
    result["fair_odds"] = 1 + result["loss_fraction"] / result["win_fraction"] if result["win_fraction"] > 1e-12 else None
    return result


def recommendation_block(pick, min_cons_ev=0.02):
    """A full-coverage label alone is not sufficient evidence for publication."""
    if pick.get("policy_version") != POLICY_VERSION:
        return "refresh_required"
    if pick.get("coverage_status") != "full" or pick.get("lambda_source") not in {"market+strength", "market+strength-cross"}:
        return "no_independent_team_ratings"
    if not pick.get("market_probability"):
        return "incomplete_two_sided_price"
    if not math.isfinite(float(pick.get("conservative_ev") or 0)) or float(pick.get("conservative_ev") or 0) < min_cons_ev:
        return "edge_not_robust"
    return None
