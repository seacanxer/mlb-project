import math
import json
import os
from datetime import datetime, timedelta

MAX_GOALS = 10
RHO_DEFAULT = -0.13

def pois_pmf(k, lam):
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

def dixon_coles_tau(x, y, lh, la, rho):
    if x == 0 and y == 0:
        return max(0.0, 1.0 - lh * la * rho)
    if x == 1 and y == 0:
        return max(0.0, 1.0 + la * rho)
    if x == 0 and y == 1:
        return max(0.0, 1.0 + lh * rho)
    if x == 1 and y == 1:
        return max(0.0, 1.0 - rho)
    return 1.0

def score_matrix(lh, la, rho=RHO_DEFAULT, max_goals=MAX_GOALS):
    m = {}
    tot = 0.0
    for x in range(max_goals + 1):
        for y in range(max_goals + 1):
            p = pois_pmf(x, lh) * pois_pmf(y, la) * dixon_coles_tau(x, y, lh, la, rho)
            m[(x, y)] = p
            tot += p
    return m, tot

def match_probs(lh, la, rho=RHO_DEFAULT, max_goals=MAX_GOALS):
    m, tot = score_matrix(lh, la, rho, max_goals)
    home = sum(p for (x, y), p in m.items() if x > y) / tot
    draw = sum(p for (x, y), p in m.items() if x == y) / tot
    away = sum(p for (x, y), p in m.items() if x < y) / tot
    return home, draw, away

def btts_prob(lh, la, rho=RHO_DEFAULT, max_goals=MAX_GOALS):
    m, tot = score_matrix(lh, la, rho, max_goals)
    return sum(p for (x, y), p in m.items() if x >= 1 and y >= 1) / tot

def _pmf_array(lam, max_goals=MAX_GOALS):
    return [pois_pmf(k, lam) for k in range(max_goals + 1)]

def over_prob(line, lh, la, max_goals=MAX_GOALS):
    lam = lh + la
    pmf = _pmf_array(lam, max_goals)
    k = int(math.floor(line))
    return 1.0 - sum(pmf[:k+1])

def under_prob(line, lh, la, max_goals=MAX_GOALS):
    lam = lh + la
    pmf = _pmf_array(lam, max_goals)
    k = int(math.floor(line))
    if abs(line - k) < 1e-9:
        return sum(pmf[:k])
    return sum(pmf[:k+1])

def _sub_lines(h):
    if abs(h % 0.5) < 1e-9:
        return [h, h]
    return [h - 0.25, h + 0.25]

def ah_payout(home_handicap, odds, home_margin):
    lines = _sub_lines(home_handicap)
    ret = 0.0
    for leg in lines:
        adj = home_margin + leg
        if adj > 1e-9:
            ret += odds
        elif abs(adj) <= 1e-9:
            ret += 1.0
    return ret / len(lines)

def ah_payout_away(away_handicap, odds, home_margin):
    lines = _sub_lines(away_handicap)
    ret = 0.0
    for leg in lines:
        adj = -home_margin + leg
        if adj > 1e-9:
            ret += odds
        elif abs(adj) <= 1e-9:
            ret += 1.0
    return ret / len(lines)

def ah_ev(home_handicap, odds, lh, la, rho=RHO_DEFAULT, max_goals=MAX_GOALS):
    m, tot = score_matrix(lh, la, rho, max_goals)
    exp_ret = 0.0
    for (x, y), p in m.items():
        exp_ret += (p / tot) * ah_payout(home_handicap, odds, x - y)
    return exp_ret - 1.0

def ah_ev_away(away_handicap, odds, lh, la, rho=RHO_DEFAULT, max_goals=MAX_GOALS):
    m, tot = score_matrix(lh, la, rho, max_goals)
    exp_ret = 0.0
    for (x, y), p in m.items():
        exp_ret += (p / tot) * ah_payout_away(away_handicap, odds, x - y)
    return exp_ret - 1.0

def shin_margin(odds):
    raw = [1.0 / o for o in odds]
    s = sum(raw)
    lo, hi = 0.0, 0.5
    for _ in range(100):
        z = (lo + hi) / 2
        denom = 1 - z
        if denom <= 0:
            hi = z
            continue
        total = 0.0
        for pi in raw:
            total += (pi / denom) + z / (denom * denom)
        if total > 1.0:
            lo = z
        else:
            hi = z
    z = (lo + hi) / 2
    denom = 1 - z
    if denom <= 0:
        return [r / s for r in raw]
    return [(r / denom + z / (denom * denom)) for r in raw]

def ev(p, odds):
    return p * odds - 1.0

def implied_prob(odds):
    return 1.0 / odds

def blend(probs_model, probs_market, w=0.5):
    return [w * pm + (1-w) * p_market for pm, p_market in zip(probs_model, probs_market)]

def fit_total_from_ou(odds_over, odds_under, line=2.5, lo=0.1, hi=6.0, steps=600):
    implied_o = implied_prob(odds_over)
    implied_u = implied_prob(odds_under)
    fair_over = implied_o / (implied_o + implied_u)
    best = None
    for i in range(steps + 1):
        lam = lo + (hi - lo) * i / steps
        p_over = over_prob(line, lam * 0.5, lam * 0.5)
        if best is None or abs(p_over - fair_over) < best[0]:
            best = (abs(p_over - fair_over), lam)
    return best[1], fair_over

def total_ev(line, side, odds, lh, la, max_goals=MAX_GOALS):
    lam = lh + la
    pmf = _pmf_array(lam, max_goals)
    if abs(line % 0.5) < 1e-9:
        legs = [(line, 1.0)]
    else:
        legs = [(line - 0.25, 0.5), (line + 0.25, 0.5)]
    exp_ret = 0.0
    for leg, w in legs:
        if abs(leg % 1.0) < 1e-9:
            i = int(leg)
            if side == "over":
                exp_ret += w * (odds * (1.0 - sum(pmf[: i + 1])) + 1.0 * pmf[i])
            else:
                exp_ret += w * odds * sum(pmf[:i])
        else:
            i = int(math.floor(leg))
            if side == "over":
                exp_ret += w * odds * (1.0 - sum(pmf[: i + 1]))
            else:
                exp_ret += w * odds * sum(pmf[: i + 1])
    return exp_ret - 1.0

def lam_from_odds(odds_home, odds_draw, odds_away, odds_over, odds_under, ou_line=2.5):
    p_h, p_d, p_a = shin_margin([odds_home, odds_draw, odds_away])
    lam_total, fair_over = fit_total_from_ou(odds_over, odds_under, ou_line)
    ratio = p_h / (p_h + p_a)
    return lam_total * ratio, lam_total * (1.0 - ratio), (p_h, p_d, p_a), fair_over

def strength_lam(home_att, away_def, away_att, home_def, league_avg, home_adv=1.08):
    lh = (home_att / league_avg) * (away_def / league_avg) * league_avg * home_adv
    la = (away_att / league_avg) * (home_def / league_avg) * league_avg
    return lh, la