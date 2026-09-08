"""Reliability diagram + Brier score on settled locks (read-only).

Buckets model probability at lock time vs realized win rate. Pushes
(won IS NULL) excluded from win rate, included in Brier as 0.5 outcome.

    python calibration_report.py [--db bets.db] [--buckets 0.5,0.55,0.6,0.65,0.7,0.8,1.01]
"""
import argparse
import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(BASE_DIR, "bets.db"))
    ap.add_argument("--buckets", default="0.5,0.55,0.6,0.65,0.7,0.8,1.01")
    args = ap.parse_args()
    edges = [float(x) for x in args.buckets.split(",")]
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cols = {r[1] for r in con.execute("PRAGMA table_info(bets)")}
    extra = ", coverage_status" if "coverage_status" in cols else ", NULL AS coverage_status"
    rows = [dict(r) for r in con.execute(CANON_CTE + f"""
        SELECT probability, won, profit{extra} FROM ranked_bets
        WHERE duplicate_rank=1 AND settled=1 AND probability IS NOT NULL""")]
    con.close()
    brier = sum((float(r["probability"]) - (1 if r["won"] == 1 else (0 if r["won"] == 0 else 0.5))) ** 2
                for r in rows) / max(len(rows), 1)
    print(f"n={len(rows)} brier={brier:.4f} (baseline coin-flip ~0.25)")
    print(f"{'bucket':>13} {'n':>5} {'decided':>8} {'pred%':>7} {'actual%':>8} {'gap':>7}")
    ece_num = 0
    for lo, hi in zip(edges[:-1], edges[1:]):
        b = [r for r in rows if lo <= float(r["probability"]) < hi]
        if not b:
            print(f"{lo:.2f}-{hi:.2f} {'0':>5}");
            continue
        pred = sum(float(r["probability"]) for r in b) / len(b)
        dec = [r for r in b if r["won"] is not None]
        act = sum(1 for r in dec if r["won"] == 1) / len(dec) if dec else 0.0
        gap = act - pred
        ece_num += abs(gap) * len(dec)
        print(f"{lo:.2f}-{hi:.2f} {len(b):>5} {len(dec):>8} {pred * 100:>6.1f} {act * 100:>7.1f} {gap * 100:>+6.1f}")
    tot_dec = sum(1 for r in rows if r["won"] is not None)
    print(f"ECE={ece_num / max(tot_dec, 1) * 100:.2f}pp over {tot_dec} decided")


if __name__ == "__main__":
    main()
