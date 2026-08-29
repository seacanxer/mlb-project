import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from model import (
    ah_ev,
    ah_ev_away,
    ah_payout,
    ah_payout_away,
    btts_prob,
    ev,
    fit_total_from_ou,
    implied_prob,
    lam_from_1x2,
    match_probs,
    over_prob,
    remove_margin,
    under_prob,
)
from main import select_top_picks
from main import analyze_match
from settlement import total_payout

TOL = 1e-3


def approx(a, b, tol=TOL):
    return abs(a - b) <= tol


def test_1x2_probs():
    h, d, a = match_probs(1.5, 1.2)
    assert approx(h, 0.4257), h
    assert approx(d, 0.2863), d
    assert approx(a, 0.2880), a
    assert approx(h + d + a, 1.0)


def test_btts():
    p = btts_prob(1.5, 1.2)
    assert approx(p, 0.5586), p


def test_ou():
    o = over_prob(2.5, 1.5, 1.2)
    u = under_prob(2.5, 1.5, 1.2)
    assert approx(o, 0.5064), o
    assert approx(u, 0.4936), u
    assert approx(o + u, 1.0)
    assert approx(ev(o, 2.10), 0.0634, 5e-3)


def test_integer_line_push():
    # Integer line 2.0: over wins 3+, under wins 0-1, total==2 pushes.
    # So o2 + u2 = 1 - P(exactly 2 goals), NOT 1.0.
    lam = 2.7
    push = math.exp(-lam) * lam ** 2 / 2.0
    o2 = over_prob(2.0, 1.5, 1.2)
    u2 = under_prob(2.0, 1.5, 1.2)
    assert approx(o2, 0.5064, 1e-3), o2
    assert approx(u2, 0.2487, 1e-3), u2
    assert approx(o2 + u2, 1.0 - push, 1e-6)


def test_quarter_line():
    o = over_prob(2.25, 1.5, 1.2)
    u = under_prob(2.25, 1.5, 1.2)
    assert approx(o + u, 1.0, 1e-6)


def test_ah_payout_venn():
    serves = {"+2": 1.95, "+1": 1.475, "0": 0.0, "-1": 0.0}
    for m, want in serves.items():
        margin = {"+2": 2, "+1": 1, "0": 0, "-1": -1}[m]
        got = ah_payout(-0.75, 1.95, margin)
        assert approx(got, want, 1e-6), (m, got)


def test_ah_quarter_payout():
    assert approx(ah_payout(-0.25, 1.95, 0), 0.5, 1e-6)  # half loss
    assert approx(ah_payout(-0.25, 1.95, 1), 1.95, 1e-6)  # full win
    assert approx(ah_payout(0.25, 1.95, 0), 1.475, 1e-6)  # half win
    assert approx(ah_payout(-0.5, 1.95, 0), 0.0, 1e-6)
    assert approx(ah_payout(-1.0, 1.95, 0), 0.0, 1e-6)


def test_ah_ev_monotonic():
    assert ah_ev(-0.75, 10.0, 1.5, 1.2) > 0
    assert ah_ev(-0.75, 1.01, 1.5, 1.2) < 0


def test_ah_away_payout():
    # Away +0.25 @1.95 vs draw: one leg wins (1.95) + one leg pushes (1.0) → 1.475
    assert approx(ah_payout_away(0.25, 1.95, 0), 1.475, 1e-6)
    # Away +0.75: away covers on draw → both legs win
    assert approx(ah_payout_away(0.75, 1.95, 0), 1.95, 1e-6)
    # Away -0.5 loses on draw
    assert approx(ah_payout_away(-0.5, 1.95, 0), 0.0, 1e-6)
    # Away +0.25 loses when home wins by 1
    assert approx(ah_payout_away(0.25, 1.95, 1), 0.0, 1e-6)


def test_margin_removal():
    p = remove_margin([1.515, 4.93, 6.55])
    assert approx(sum(p), 1.0)
    assert all(x > 0 for x in p)
    assert p[0] > p[1] > p[2]


def test_fit_total():
    lam, fair_over = fit_total_from_ou(1.51, 2.42, 2.5)
    assert 2.9 < lam < 3.4, lam
    assert 0.6 < fair_over < 0.64, fair_over


def test_1x2_only_lambda_fit_is_independent_of_totals_market():
    lh, la, target = lam_from_1x2(2.0, 3.4, 3.8)
    fitted = match_probs(lh, la)
    assert sum(abs(a - b) for a, b in zip(fitted, target)) < 0.10


def test_implied():
    assert approx(implied_prob(2.0), 0.5)
    assert approx(ev(0.5, 2.1), 0.05)


def test_top_picks_are_capped_diversified_and_one_per_match():
    candidates = []
    markets = ["1x2", "ah", "ou", "btts"]
    for i in range(20):
        candidates.append({
            "match": f"Home {i // 2} vs Away {i // 2}",
            "start_ts": i // 2,
            "market": markets[i % 4],
            "pick": f"Pick {i}",
            "probability": 0.58,
            "odds": 1.9,
            "ev": 0.10,
        })
    picks = select_top_picks(candidates, limit=8, per_market=2)
    assert len(picks) <= 8
    assert len({(p["match"], p["start_ts"]) for p in picks}) == len(picks)
    assert all(sum(1 for p in picks if p["market"] == market) <= 2 for market in markets)
    assert all(p["locked"] for p in picks)


def test_btts_yes_and_no_are_evaluated_when_prices_exist():
    market = {
        "home": "A", "away": "B", "league": "Test", "start_ts": 1,
        "odds_1x2": {1: 2.2, 2: 3.2, 3: 3.2},
        "odds_ou": {2.5: {9: 2.0, 10: 2.0}},
        "odds_ah": {}, "odds_btts": {"yes": 2.2, "no": 2.2},
    }
    picks = analyze_match(market, 1.5, 1.2, min_odds=1.66, min_ev=-1)
    btts = {p["pick"] for p in picks if p["market"] == "btts"}
    assert btts == {"BTTS Yes", "BTTS No"}


def test_total_quarter_line_settlement():
    assert approx(total_payout(2.25, "over", 1.90, 2), 0.5, 1e-9)
    assert approx(total_payout(2.75, "over", 1.90, 3), 1.45, 1e-9)
    assert approx(total_payout(3.0, "under", 1.90, 3), 1.0, 1e-9)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
