"""Registered chronological experiments: market baseline vs model.

Every run — good or bad — appends ONE row per league to
research/experiments.jsonl with full params. Never tune on the same
rows you report: pass --train-until to split fit/selection windows
(the model path itself stays OOS via previous-season ratings).

Baseline (market): OU 2.5 shorter-odds side, flat 1u, odds >= min_odds.
Model: backtest_one official path (production parity, OOS ratings).

    python run_experiment.py --name v42-vs-baseline --leagues E0 SP1 --season 2526
"""
import argparse
import json
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import scraper_historical as sh
from main import backtest_one
from settlement import total_payout
from strength_rating import parse_fd_date, prev_season_code

LOG_PATH = os.path.join(BASE_DIR, "research", "experiments.jsonl")


def run_league(code, season, min_odds, min_ev):
    rows = [sh.normalize(r) for r in sh.load_rows(sh.download(code, season, out_dir=os.path.join(BASE_DIR, "data")))]
    rows = sorted(
        (r for r in rows if r.get("fthg") is not None and parse_fd_date(r.get("date"))),
        key=lambda r: parse_fd_date(r["date"]))
    base = {"n": 0, "profit": 0.0, "wins": 0}
    model = {"n": 0, "profit": 0.0, "wins": 0}
    ledger, skipped = {}, 0
    for r in rows:
        total = r["fthg"] + r["ftag"]
        # --- market baseline: shorter side of OU 2.5 ---
        try:
            oov, oun = r["odds_over"], r["odds_under"]
            if oov and oun:
                side, odds = ("over", oov) if oov <= oun else ("under", oun)
                if odds >= min_odds:
                    profit = total_payout(2.5, side, odds, total) - 1.0
                    base["n"] += 1
                    base["profit"] += profit
                    base["wins"] += 1 if profit > 0 else 0
        except Exception:
            pass
        # --- model path (production parity, previous-season ratings) ---
        try:
            res = backtest_one(
                r, min_odds=min_odds, min_ev=min_ev, ledger=ledger,
                league_code=code, rating_season=prev_season_code(season),
                strength_weight=0.4)
        except Exception:
            skipped += 1
            continue
        for p in res.get("picks", []):
            model["n"] += 1
            model["profit"] += p.get("profit", 0.0) or 0.0
            model["wins"] += 1 if p.get("won") else 0
    for d in (base, model):
        d["profit"] = round(d["profit"], 2)
        d["roi_pct"] = round(d["profit"] / d["n"] * 100, 2) if d["n"] else None
        d["hit_pct"] = round(d["wins"] / d["n"] * 100, 2) if d["n"] else None
    return {"league": code, "season": season, "rows": len(rows), "skipped": skipped,
            "baseline": base, "model": model}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--leagues", nargs="+", default=["E0"])
    ap.add_argument("--season", default="2526")
    ap.add_argument("--min-odds", type=float, default=1.50)
    ap.add_argument("--min-ev", type=float, default=0.0)
    ap.add_argument("--log", default=LOG_PATH)
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.log), exist_ok=True)
    print(f"{'league':>6} {'n_base':>7} {'roi_b':>8} {'n_model':>8} {'roi_m':>8}")
    with open(args.log, "a", encoding="utf-8") as f:
        for code in args.leagues:
            item = run_league(code, args.season, args.min_odds, args.min_ev)
            row = {"ts": time.time(), "name": args.name,
                   "min_odds": args.min_odds, "min_ev": args.min_ev, **item}
            f.write(json.dumps(row) + "\n")
            b, m = item["baseline"], item["model"]
            print(f"{code:>6} {b['n']:>7} {str(b['roi_pct']):>8} {m['n']:>8} {str(m['roi_pct']):>8}")
    print(f"logged to {args.log}")


if __name__ == "__main__":
    main()
