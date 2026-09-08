"""Closing Line Value: locked odds vs last pre-kickoff intel snapshot.

Uses intel_snapshots (opening/movement log); the latest observation at or
before kickoff proxies the closing price. Positive CLV = beating the close.
Read-only. Reports coverage when snapshots are missing.

    python clv_report.py [--db bets.db]
"""
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
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(BASE_DIR, "bets.db"))
    args = ap.parse_args()
    if not os.path.exists(args.db):
        print(f"no db at {args.db}")
        return
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "intel_snapshots" not in tables:
        print("intel_snapshots table missing — no movement log, CLV unavailable")
        return
    bets = [dict(r) for r in con.execute(CANON_CTE + """
        SELECT match, market, pick, odds, start_ts, won FROM ranked_bets
        WHERE duplicate_rank=1 AND settled=1 AND odds IS NOT NULL AND start_ts IS NOT NULL""")]
    snaps = [dict(r) for r in con.execute(
        "SELECT match_id, observed_at, market, line, side, odds FROM intel_snapshots")]
    con.close()
    from datetime import datetime, timezone

    def ts(s):
        try:
            return datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            return None

    clvs, missing = [], 0
    for b in bets:
        kick = float(b["start_ts"])
        cands = [s for s in snaps if (ts(s["observed_at"]) or 0) <= kick]
        if not cands:
            missing += 1
            continue
        # closest snapshot at/under kickoff; match by market family only
        fam = "ou" if b["market"] == "ou" else ("ah" if b["market"] == "ah" else None)
        cands = [s for s in cands if s["market"] == fam]
        if not cands:
            missing += 1
            continue
        close = max(cands, key=lambda s: ts(s["observed_at"]) or 0)
        try:
            o, c = float(b["odds"]), float(close["odds"])
            clvs.append((1.0 / c - 1.0 / o) * 100.0)
        except (TypeError, ZeroDivisionError):
            missing += 1
    print(f"settled={len(bets)} clv_coverage={len(clvs)} missing={missing}")
    if clvs:
        clvs.sort()
        mean = sum(clvs) / len(clvs)
        print(f"mean_CLV={mean:+.2f}pp median={clvs[len(clvs)//2]:+.2f}pp "
              f"positive_share={sum(1 for v in clvs if v > 0)/len(clvs)*100:.1f}%")
        print("(CLV>0 consistently = real edge signal, independent of short-term ROI)")


if __name__ == "__main__":
    main()
