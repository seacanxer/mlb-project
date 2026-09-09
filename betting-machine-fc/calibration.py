"""Chronological Platt calibration per market — attach-only, never gating.

Fits P(win) ~ sigmoid(a + b * logit(model_p)) on settled locks via IRLS
(stdlib only). Outputs are ATTACHED to picks as calibrated_prob and must
never drive selection until validated out-of-sample: a calibrator fit on
past slates can silently invert on regime change. Pushes (won IS NULL)
are excluded from the fit. CalibratedEV stays null when no fresh
calibrator exists.

    python calibration.py --db bets.db --out data/calibrators.json [--since 2026-08-01] [--until 2026-09-01]
"""
import argparse
import json
import math
import os
import sqlite3
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

CALIBRATOR_TTL_S = 30 * 24 * 3600
MIN_FIT_N = 50

CANON_CTE = '''
    WITH ranked_bets AS (
        SELECT bets.*,
               ROW_NUMBER() OVER (
                   PARTITION BY COALESCE(NULLIF(source_match_id, ''), LOWER(TRIM(match)), ''),
                                COALESCE(date(start_ts, 'unixepoch'), ''),
                                COALESCE(market, ''), COALESCE(pick, '')
                   ORDER BY settled DESC, id ASC
               ) AS duplicate_rank
        FROM bets
    )
'''


def _sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def _logit(p):
    p = min(0.999, max(0.001, p))
    return math.log(p / (1.0 - p))


def fit_platt(pairs):
    """IRLS logistic regression on single feature logit(p). Returns (a, b).
    Falls back to identity (0.0, 1.0) when the fit is degenerate."""
    xs = [_logit(p) for p, _ in pairs]
    ys = [float(y) for _, y in pairs]
    a, b = 0.0, 1.0
    try:
        for _ in range(50):
            ga = gb = haa = hab = hbb = 0.0
            for x, y in zip(xs, ys):
                q = _sigmoid(a + b * x)
                w = max(q * (1.0 - q), 1e-9)
                ga += q - y
                gb += (q - y) * x
                haa += w
                hab += w * x
                hbb += w * x * x
            det = haa * hbb - hab * hab
            if abs(det) < 1e-12:
                return 0.0, 1.0
            da = (ga * hbb - gb * hab) / det
            db = (haa * gb - hab * ga) / det
            a -= da
            b -= db
            if abs(da) + abs(db) < 1e-9:
                break
    except (OverflowError, ValueError):
        return 0.0, 1.0
    if not (math.isfinite(a) and math.isfinite(b)) or b < 0:
        # Negative slope = anti-calibration; keep identity, flag it.
        return 0.0, 1.0
    return round(a, 4), round(b, 4)


def apply_platt(prob, calibrator):
    if not calibrator:
        return None
    try:
        return round(_sigmoid(calibrator["a"] + calibrator["b"] * _logit(float(prob))), 4)
    except (KeyError, TypeError, ValueError):
        return None


def load_calibrators(path=None):
    """Fresh calibrator mapping or None (stale/missing/invalid)."""
    path = path or os.path.join(BASE_DIR, "data", "calibrators.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if time.time() - payload.get("fitted_at", 0) > CALIBRATOR_TTL_S:
            return None
        cal = payload.get("markets", {})
        return cal or None
    except Exception:
        return None


def _brier(pairs):
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(BASE_DIR, "bets.db"))
    ap.add_argument("--out", default=os.path.join(BASE_DIR, "data", "calibrators.json"))
    ap.add_argument("--since", default=None)
    ap.add_argument("--until", default=None)
    args = ap.parse_args()
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    filt = ""
    if args.since:
        filt += f" AND settled_at >= '{args.since}'"
    if args.until:
        filt += f" AND settled_at < '{args.until}'"
    rows = [dict(r) for r in con.execute(CANON_CTE + f"""
        SELECT market, probability, won FROM ranked_bets
        WHERE duplicate_rank=1 AND settled=1 AND won IS NOT NULL
          AND probability IS NOT NULL{filt}""")]
    con.close()
    by_market = {}
    for r in rows:
        try:
            p = float(r["probability"])
            if 0 < p < 1:
                by_market.setdefault(r["market"] or "?", []).append((p, int(r["won"])))
        except (TypeError, ValueError):
            continue
    markets = {}
    for market, pairs in sorted(by_market.items()):
        if len(pairs) < MIN_FIT_N:
            print(f"{market}: n={len(pairs)} < {MIN_FIT_N}, skipped")
            continue
        a, b = fit_platt(pairs)
        cal = [_sigmoid(a + b * _logit(p)) for p, _ in pairs]
        markets[market] = {
            "a": a, "b": b, "n": len(pairs),
            "brier_before": round(_brier([(p, y) for p, y in pairs]), 4),
            "brier_after": round(_brier(list(zip(cal, [y for _, y in pairs]))), 4),
        }
        m = markets[market]
        print(f"{market}: n={m['n']} a={a} b={b} brier {m['brier_before']} -> {m['brier_after']}")
    payload = {"fitted_at": time.time(), "db": args.db,
               "since": args.since, "until": args.until, "markets": markets}
    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
