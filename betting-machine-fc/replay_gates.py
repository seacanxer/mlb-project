"""Replay gate grids over stored scan candidates + join settled ROI.

Reads matches_detailed.json "picks" (post-analyze candidates), applies
select_top_picks under a gate grid, and joins bets.db settled profits by
(match, market, pick) for an ROI estimate. Research-only: never writes picks.

    python replay_gates.py [--db bets.db] [--limit 200]
"""
import argparse
import json
import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from main import analyze_match, select_top_picks
from prediction import build_projection, build_projection_fallback

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


def load_settled(db_path):
    if not os.path.exists(db_path):
        return {}
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(CANON_CTE + """
        SELECT match, market, pick, profit, won FROM ranked_bets
        WHERE duplicate_rank=1 AND settled=1""").fetchall()
    con.close()
    out = {}
    for r in rows:
        out.setdefault((str(r["match"]).lower(), r["market"], r["pick"]), []).append(float(r["profit"] or 0))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(BASE_DIR, "bets.db"))
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()
    det = json.load(open(os.path.join(BASE_DIR, "matches_detailed.json"), encoding="utf-8"))
    # Re-run CURRENT analyze on stored odds (stored picks are stale artifacts
    # from older gates and lack derived fields like has_both_markets).
    cands = []
    for d in det:
        o = d.get("info") or {}
        try:
            proj = build_projection(o)
        except Exception as exc:
            try:
                proj = build_projection_fallback(o, reason=exc)
            except Exception:
                continue
        try:
            cands.extend(analyze_match(
                o, proj["home"], proj["away"], min_odds=1.50, min_ev=0.0,
                projection_meta=proj, active_markets=("ou", "ah")))
        except Exception:
            continue
    settled = load_settled(args.db)
    print(f"matches={len(det)} candidates={len(cands)} settled_lookup={len(settled)}")
    print(f"{'cons_ev':>8} {'margin':>7} {'min_odds':>9} {'n':>5} {'matched':>8} {'roi%':>8}")
    for cons_ev in (0.005, 0.01, 0.02):
        for margin in (0.0, 0.03, 0.05):
            for min_odds in (1.50, 1.64):
                sel = select_top_picks(
                    cands, limit=args.limit, per_market=25, per_match=1,
                    min_ev=0.0, min_edge=0.02, min_odds=min_odds, max_odds=2.75,
                    top_signal_limit=5, include_shadow=True,
                    shadow_min_cons_ev=cons_ev, shadow_prob_margin=margin,
                    min_edge_official=0.015, min_edge_shadow=0.02,
                    min_edge_watch=0.05)
                hits = []
                for p in sel:
                    key = (str(p.get("match", "")).lower(), p.get("market"), p.get("pick"))
                    hits.extend(settled.get(key, []))
                roi = (sum(hits) / len(hits) * 100) if hits else None
                roi_s = f"{roi:+.1f}" if roi is not None else "n/a"
                print(f"{cons_ev:>8.3f} {margin:>7.2f} {min_odds:>9.2f} {len(sel):>5} {len(hits):>8} {roi_s:>8}")


if __name__ == "__main__":
    main()
