#!/usr/bin/env python3
"""Settle FC picks that have kicked off using results feeds.

Flow:
  1. load bets.db — find unsettled bets with start_ts <= now - SETTLE_DELAY
  2. for each, fetch result from FlashScore (primary) then TheSportsDB/OpenLigaDB
  3. settle via the same payout math as the engine (markets.settle_score)
  4. write back to bets.db (locked->settled) and refresh tracker_snapshot.json

Run: betting-machine-fc/venv/bin/python scripts/fc-settle-live.py
"""
import json
import os
import sys
import time
import sqlite3
import subprocess
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FC_DIR = os.path.join(BASE_DIR, 'betting-machine-fc')
sys.path.insert(0, FC_DIR)

from football_formula_engine.markets import settle_score  # noqa: E402
import scores_flashscore  # noqa: E402
import scores_alt  # noqa: E402

SETTLE_DELAY_S = 6300  # 1h45m after kickoff
DB_PATH = os.path.join(FC_DIR, 'bets.db')
SNAPSHOT_SCRIPT = os.path.join(BASE_DIR, 'scripts', 'fc-snapshot.py')


def parse_line(pick_str, market):
    if market in ('1x2', 'btts'):
        return None
    import re
    m = re.search(r'(-?\d+(?:\.\d+)?)$', pick_str)
    if not m:
        return None
    return int(round(float(m.group(1)) * 4))


def settle_bet(market, pick_label, odds, home_goals, away_goals):
    """Return (won: int|None, profit: float). won=None -> push/void."""
    side = pick_label.lower()
    if market == 'ou':
        line_q = parse_line(pick_label, market)
        if line_q is None:
            return None
        payout = settle_score('ou', 'over' if 'over' in side else 'under', line_q, home_goals, away_goals)
    elif market == 'ah':
        line_q = parse_line(pick_label, market)
        if line_q is None:
            return None
        payout = settle_score('ah', 'home' if 'home' in side else 'away', line_q, home_goals, away_goals)
    elif market == '1x2':
        side_map = {'home': 'home', 'draw': 'draw', 'away': 'away'}
        payout = settle_score('1x2', side_map.get(side, side), None, home_goals, away_goals)
    elif market == 'btts':
        side_map = {'btts yes': 'yes', 'btts no': 'no', 'yes': 'yes', 'no': 'no'}
        payout = settle_score('btts', side_map.get(side, side), None, home_goals, away_goals)
    else:
        return None

    if payout.push == 1.0:
        return None, 0.0
    profit = ((payout.full_win + 0.5 * payout.half_win) * (odds - 1.0)
              - payout.full_loss - 0.5 * payout.half_loss)
    return (1 if profit > 0 else 0), round(profit, 2)


def result_for_bet(home, away, kickoff_ts, lookup_fs, lookup_alt):
    kickoff_date = datetime.fromtimestamp(kickoff_ts, tz=timezone.utc).date()
    row = scores_flashscore.find_result(home, away, lookup_fs, kickoff_date)
    if row and row.get('score_status') == 'final':
        return row['home_score'], row['away_score'], 'flashscore'
    row = scores_alt.find_result(home, away, lookup_alt, kickoff_date)
    if row and row.get('score_status') == 'final':
        return row['home_score'], row['away_score'], 'alt'
    return None


def main():
    if not os.path.exists(DB_PATH):
        print(json.dumps({'status': 'error', 'message': 'bets.db missing'}))
        return 1

    now = time.time()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    unsettled = conn.execute(
        'SELECT id, match, home, away, league, start_ts, market, pick, odds, source_match_id FROM bets WHERE settled=0 AND start_ts <= ?',
        (now - SETTLE_DELAY_S,),
    ).fetchall()

    if not unsettled:
        print(json.dumps({'status': 'ok', 'settled': 0, 'pending': 0}))
        return 0

    lookup_fs = scores_flashscore.fetch_recent_results(days=14)
    lookup_fs_idx = scores_flashscore.build_lookup(lookup_fs)
    lookup_alt = scores_alt.fetch_recent_results(days=14)
    lookup_alt_idx = scores_alt.build_lookup(lookup_alt)

    settled_count = 0
    for bet in unsettled:
        result = result_for_bet(bet['home'], bet['away'], bet['start_ts'], lookup_fs_idx, lookup_alt_idx)
        if not result:
            continue
        home_goals, away_goals, source = result
        outcome = settle_bet(bet['market'], bet['pick'], bet['odds'], home_goals, away_goals)
        if outcome is None:
            continue
        won, profit = outcome
        settled_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            'UPDATE bets SET settled=1, won=?, profit=?, settled_at=?, home_score=?, away_score=?, score_status=? WHERE id=?',
            (won, profit, settled_at, home_goals, away_goals, 'final', bet['id']),
        )
        settled_count += 1

    conn.commit()
    remaining = conn.execute('SELECT COUNT(*) c FROM bets WHERE settled=0').fetchone()['c']
    conn.close()

    subprocess.run([sys.executable, SNAPSHOT_SCRIPT, '--db', DB_PATH], check=True)

    print(json.dumps({
        'status': 'ok', 'settled': settled_count,
        'to_settle': len(unsettled), 'remaining': remaining,
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
