#!/usr/bin/env python3
"""Build betting-machine-fc/tracker_snapshot.json from bets.db.

The /api/fc/tracker route serves this file VERBATIM — the dashboard is a
mirror, not a second calculator (brief section 10.2 / 11.4.7). All aggregation
logic here mirrors the deleted engine (db.get_roi / get_market_performance /
get_roi_by_version / classify_settlement_status from commit b306fe8), including
the canonical duplicate-rank CTE, so numbers stay bit-for-bit comparable when
the engine is restored.

Usage (on VPS, after settlement or on a cron):
    python3 scripts/fc-snapshot.py [--db betting-machine-fc/bets.db]
"""
import argparse
import datetime
import json
import math
import os
import sqlite3
import sys
import time

CANONICAL_CTE = """
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
"""

KEYS = ['id', 'match', 'home', 'away', 'league', 'start_ts', 'market', 'pick',
        'odds', 'ev', 'probability', 'placed_at', 'settled', 'won', 'profit',
        'settled_at', 'source_match_id', 'home_score', 'away_score',
        'score_status', 'score_updated_at']


def classify(bet, now):
    kickoff = float(bet.get('start_ts') or 0)
    if bet.get('settled'):
        return 'settled'
    if not kickoff or now < kickoff:
        return 'locked'
    if now < kickoff + 6300:
        return 'live'
    return 'overdue'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=os.path.join('betting-machine-fc', 'bets.db'))
    ap.add_argument('--out', default=os.path.join('betting-machine-fc', 'tracker_snapshot.json'))
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print(f'bets.db not found at {args.db}; writing empty snapshot', file=sys.stderr)
        snap = {
            'summary': {'locked_picks': 0, 'settled_picks': 0, 'wins': 0, 'losses': 0,
                        'pushes': 0, 'profit_units': 0.0, 'roi_pct': 0.0, 'hit_rate_pct': 0.0},
            'locked': [], 'live': [], 'overdue': [], 'settled': [],
            'status_counts': {'locked': 0, 'live': 0, 'overdue': 0, 'settled': 0},
            'market_performance': [], 'by_version': [], 'unit_size': 1.0,
        }
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(snap, f, ensure_ascii=False, indent=2)
        return 0

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    now = time.time()

    rows = [dict(r) for r in conn.execute(
        CANONICAL_CTE + 'SELECT * FROM ranked_bets WHERE duplicate_rank=1 ORDER BY start_ts DESC, id ASC').fetchall()]
    bets = [{k: r.get(k) for k in KEYS} for r in rows]

    unsettled = [b for b in bets if not b.get('settled')]
    settled = [b for b in bets if b.get('settled')]
    buckets = {'locked': [], 'live': [], 'overdue': [], 'settled': settled}
    for b in unsettled:
        s = classify(b, now)
        b = dict(b)
        b['settlement_status'] = s
        b['timing_status'] = s
        buckets[s].append(b)
    for b in buckets['settled']:
        b['settlement_status'] = 'settled'
        b['timing_status'] = 'settled'

    total = len(settled)
    wins = sum(1 for b in settled if b.get('won') == 1)
    losses = sum(1 for b in settled if b.get('won') == 0)
    pushes = sum(1 for b in settled if b.get('won') is None)
    profit = sum(float(b.get('profit') or 0.0) for b in settled)
    roi = (profit / total * 100) if total else 0.0
    decided = wins + losses
    hit = (wins / decided * 100) if decided else 0.0
    dupes = conn.execute(
        CANONICAL_CTE + 'SELECT COUNT(*) FROM ranked_bets WHERE duplicate_rank > 1').fetchone()[0]

    summary = {
        'locked_picks': len(buckets['locked']),
        'settled_picks': total,
        'wins': wins, 'losses': losses, 'pushes': pushes,
        'profit_units': round(profit, 2),
        'roi_pct': round(roi, 2),
        'hit_rate_pct': round(hit, 2),
        'duplicates_hidden': dupes or 0,
        'pending_picks': len(unsettled),
        'live_picks': len(buckets['live']),
        'overdue_picks': len(buckets['overdue']),
    }

    mkt_rows = conn.execute(
        CANONICAL_CTE + """SELECT market, COUNT(*) AS bets,
               SUM(CASE WHEN won=1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN won=0 THEN 1 ELSE 0 END) AS losses,
               SUM(CASE WHEN won IS NULL THEN 1 ELSE 0 END) AS pushes,
               COALESCE(SUM(profit), 0) AS profit
            FROM ranked_bets WHERE duplicate_rank=1 AND settled=1
            GROUP BY market ORDER BY market""").fetchall()
    market_performance = []
    for r in mkt_rows:
        b, w, l = r['bets'] or 0, r['wins'] or 0, r['losses'] or 0
        dec = w + l
        p = float(r['profit'] or 0.0)
        market_performance.append({
            'market': r['market'] or 'unknown', 'bets': b, 'wins': w, 'losses': l,
            'pushes': r['pushes'] or 0,
            'win_rate_pct': round(w / dec * 100, 2) if dec else 0.0,
            'loss_rate_pct': round(l / dec * 100, 2) if dec else 0.0,
            'profit_units': round(p, 2),
            'roi_pct': round(p / b * 100, 2) if b else 0.0,
        })

    has_audit = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='bet_audit'").fetchone()[0]
    by_version = []
    if has_audit:
        v_rows = conn.execute(
            CANONICAL_CTE + """SELECT COALESCE(a.formula_version, 'unknown') AS formula_version,
               COALESCE(a.selection_status, 'unknown') AS selection_status,
               COUNT(*) AS bets,
               COALESCE(SUM(CASE WHEN b.won=1 THEN 1 ELSE 0 END), 0) AS wins,
               COALESCE(SUM(CASE WHEN b.won=0 THEN 1 ELSE 0 END), 0) AS losses,
               COALESCE(SUM(b.profit), 0) AS profit,
               COALESCE(AVG(b.profit * b.profit), 0) AS mean_sq
            FROM ranked_bets b LEFT JOIN bet_audit a ON a.bet_id = b.id
            WHERE b.duplicate_rank=1 AND b.settled=1
            GROUP BY formula_version, selection_status
            ORDER BY formula_version, selection_status""").fetchall()
        for r in v_rows:
            n = r['bets'] or 0
            p = float(r['profit'] or 0.0)
            mean = p / n if n else 0.0
            var = max(float(r['mean_sq'] or 0.0) - mean * mean, 0.0)
            hw = 1.96 * math.sqrt(var / n) * 100 if n > 1 else None
            by_version.append({
                'formula_version': r['formula_version'], 'selection_status': r['selection_status'],
                'bets': n, 'wins': r['wins'] or 0, 'losses': r['losses'] or 0,
                'profit_units': round(p, 2),
                'roi_pct': round(p / n * 100, 2) if n else 0.0,
                'ci95_hw_pct': round(hw, 2) if hw is not None else None,
            })
    conn.close()

    snap = {
        'summary': summary,
        'locked': buckets['locked'], 'live': buckets['live'],
        'overdue': buckets['overdue'], 'settled': buckets['settled'],
        'status_counts': {k: len(v) for k, v in buckets.items()},
        'market_performance': market_performance,
        'by_version': by_version,
        'unit_size': 1.0,
        'built_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    print(f'snapshot: settled={total} profit={profit:.2f} roi={roi:.2f}% -> {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
