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
    match_probs,
    over_prob,
    remove_margin,
    under_prob,
)

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


def test_implied():
    assert approx(implied_prob(2.0), 0.5)
    assert approx(ev(0.5, 2.1), 0.05)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed")