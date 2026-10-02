#!/usr/bin/env python3
"""Settle FC picks that have kicked off using results feeds.

Flow:
  1. load bets.db — find due singles and parlay legs
  2. fetch only their kickoff-date pages from FlashScore, FotMob and league-scoped
     ESPN in parallel; query TheSportsDB/OpenLigaDB only for unresolved fixtures
  3. settle via the same payout math as the engine (markets.settle_score)
  4. write back to bets.db (locked->settled) and refresh tracker_snapshot.json

Run: betting-machine-fc/venv/bin/python scripts/fc-settle-live.py
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps
import json
import math
import os
import sys
import tempfile
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
import scores_espn  # noqa: E402
import scores_fotmob  # noqa: E402

SETTLE_DELAY_S = 6300  # 1h45m after kickoff
DB_PATH = os.path.join(FC_DIR, 'bets.db')
SNAPSHOT_SCRIPT = os.path.join(BASE_DIR, 'scripts', 'fc-snapshot.py')
FETCH_WORKERS = 4


def serialize_settlement(func):
    """Prevent cron, API refreshes and operator retries from overlapping."""
    @wraps(func)
    def wrapped(*args, **kwargs):
        lock_path = os.environ.get('FC_SETTLE_LOCK_PATH',
                                   os.path.join(tempfile.gettempdir(), 'fc-settle-live.lock'))
        os.makedirs(os.path.dirname(os.path.abspath(lock_path)), exist_ok=True)
        handle = open(lock_path, 'a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b'0')
                    handle.flush()
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    print(json.dumps({'status': 'busy', 'message': 'Settlement lain sedang berjalan.'}))
                    return 0
                unlock = lambda: (handle.seek(0), msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1))
            else:
                import fcntl
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    print(json.dumps({'status': 'busy', 'message': 'Settlement lain sedang berjalan.'}))
                    return 0
                unlock = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            try:
                return func(*args, **kwargs)
            finally:
                unlock()
        finally:
            handle.close()
    return wrapped


def parse_line(pick_str, market):
    if market in ('1x2', 'btts'):
        return None
    import re
    m = re.search(r'(-?\d+(?:\.\d+)?)$', pick_str)
    if not m:
        return None
    quarters = float(m.group(1)) * 4
    return int(quarters) if quarters.is_integer() else None


def settle_bet(market, pick_label, odds, home_goals, away_goals):
    """Return (won: int|None, profit: float). won=None -> push/void."""
    side = pick_label.strip().lower()
    if not math.isfinite(odds) or odds <= 1:
        raise ValueError('Invalid decimal odds')
    if market == 'ou':
        line_q = parse_line(pick_label, market)
        if line_q is None:
            return None
        token = side.split(' ', 1)[0]
        if token not in ('over', 'under'):
            raise ValueError('Unknown OU side')
        payout = settle_score('ou', token, line_q, home_goals, away_goals)
    elif market == 'ah':
        line_q = parse_line(pick_label, market)
        if line_q is None:
            return None
        tokens = side.split()
        token = tokens[1] if tokens and tokens[0] == 'ah' and len(tokens) > 1 else tokens[0]
        if token not in ('home', 'away'):
            raise ValueError('Unknown AH side')
        payout = settle_score('ah', token, line_q, home_goals, away_goals)
    elif market == '1x2':
        token = side.split(' ', 1)[0]
        if token not in ('home', 'draw', 'away'):
            raise ValueError('Unknown 1X2 side')
        payout = settle_score('1x2', token, None, home_goals, away_goals)
    elif market == 'btts':
        side_map = {'btts yes': 'yes', 'btts no': 'no', 'yes': 'yes', 'no': 'no'}
        if side not in side_map:
            raise ValueError('Unknown BTTS side')
        payout = settle_score('btts', side_map[side], None, home_goals, away_goals)
    else:
        return None

    if payout.push == 1.0:
        return None, 0.0
    profit = ((payout.full_win + 0.5 * payout.half_win) * (odds - 1.0)
              - payout.full_loss - 0.5 * payout.half_loss)
    return (1 if profit > 0 else 0), round(profit, 8)


# ---- Secondary (corner/card) settlement ------------------------------------
# House-rules mapping (1xbit FT sub-games TI=2/8/10; FotMob actuals):
#   corners_ou   total = HC + AC (all corners, incl. injury time; extra-time
#                excluded — regulation only). Push (actual == line) = void.
#   corner_hdp   diff = HC - AC plus the handicap line, settled with the same
#                Asian math as goals AH (settle_score 'ah'). Push = void.
#   cards_ou     booking POINTS total = home_points + away_points where
#                points = yellows*1 + reds*2 per side (football-data
#                convention HY+AY+2*(HR+AR), same as the model and backtest).
#                A second yellow therefore counts 1 (yellow) + 2 (red) = 3,
#                matching 1xbit "booking points" convention; books that count
#                cards (not points) need a different total and must NOT reuse
#                this path. Push = void.
#   team_cards_ou  same points convention, one side only (team='home'/'away').
#   red_card     yes wins iff (HR + AR) > 0, i.e. any direct red or second
#                yellow shown in regulation. No line, no push.
# Actuals source: FotMob match_stats() (scripts/fc-fetch-match-stats.py) via
# {code}_stat_history.csv — HC/AC/HY/AY/HR/AR + Referee. Live auto-wiring is
# intentionally NOT done here yet: secondary picks are still projection-only
# (locked=False, never in bets.db), so there is nothing to settle. These pure
# functions exist so EV/settlement is ready when a verified quote source
# promotes a secondary market to lockable.
def settle_secondary_bet(market, side, line_quarters, odds, home_corners=None,
                         away_corners=None, home_points=None, away_points=None,
                         red_total=None, team=None):
    """Settle one secondary leg. Returns (won|None, profit); None = skip.

    side: 'over'/'under' for *_ou, 'home'/'away' for corner_hdp,
          'yes'/'no' for red_card. team: required 'home'/'away' for
    team_cards_ou. line_quarters: int quarter-units (None only for red_card).
    Missing actuals -> None (unresolved, never a loss).
    """
    if not math.isfinite(odds) or odds <= 1:
        raise ValueError('Invalid decimal odds')
    norm_side = str(side or '').strip().lower()
    if market in ('corners_ou', 'cards_ou'):
        if norm_side not in ('over', 'under'):
            raise ValueError('Unknown secondary O/U side')
        if line_quarters is None or line_quarters < 0:
            return None
        if market == 'corners_ou':
            if home_corners is None or away_corners is None:
                return None
            home_value, away_value = int(home_corners), int(away_corners)
        else:
            if home_points is None or away_points is None:
                return None
            home_value, away_value = int(home_points), int(away_points)
        payout = settle_score('ou', norm_side, int(line_quarters), home_value, away_value)
    elif market == 'corner_hdp':
        if norm_side not in ('home', 'away'):
            raise ValueError('Unknown corner handicap side')
        if line_quarters is None:
            return None
        if home_corners is None or away_corners is None:
            return None
        payout = settle_score('ah', norm_side, int(line_quarters),
                              int(home_corners), int(away_corners))
    elif market == 'team_cards_ou':
        if norm_side not in ('over', 'under'):
            raise ValueError('Unknown secondary O/U side')
        if team not in ('home', 'away'):
            return None
        if home_points is None or away_points is None:
            return None
        if line_quarters is None or line_quarters < 0:
            return None
        # Reuse total math with the other side zeroed: total == side points.
        other = 0
        mine = int(home_points) if team == 'home' else int(away_points)
        payout = settle_score('ou', norm_side, int(line_quarters), mine, other)
    elif market == 'red_card':
        if norm_side not in ('yes', 'no'):
            raise ValueError('Unknown red-card side')
        if red_total is None:
            return None
        won_side = 'yes' if int(red_total) > 0 else 'no'
        if norm_side != won_side:
            return 0, round(-1.0, 8)
        return 1, round(odds - 1.0, 8)
    else:
        return None
    if payout.push == 1.0:
        return None, 0.0
    profit = ((payout.full_win + 0.5 * payout.half_win) * (odds - 1.0)
              - payout.full_loss - 0.5 * payout.half_loss)
    return (1 if profit > 0 else 0), round(profit, 8)


def result_for_bet(home, away, kickoff_ts, lookup_fs, lookup_alt, lookup_espn=None, lookup_fotmob=None):
    kickoff_date = datetime.fromtimestamp(kickoff_ts, tz=timezone.utc).date()
    for source, finder, lookup in (
        ('flashscore', scores_flashscore.find_result, lookup_fs or {}),
        ('alt', scores_alt.find_result, lookup_alt or {}),
        ('fotmob', scores_fotmob.find_result, lookup_fotmob or {}),
        ('espn', scores_espn.find_result, lookup_espn or {}),
    ):
        row = finder(home, away, lookup, kickoff_date)
        if not row:
            continue
        period = str(row.get('period') or '').strip().lower()
        if period not in ('90min', 'unknown'):
            continue
        # These feeds return completed games only, but use different field names:
        # FlashScore/TheSportsDB/OpenLigaDB provide home_goals/away_goals and
        # do not include score_status. Accept explicit statuses only when final.
        status = str(row.get('score_status') or row.get('status') or '').strip().lower()
        if status and status not in ('final', 'ft', 'finished', 'match finished'):
            continue
        home_goals = row.get('home_score', row.get('home_goals'))
        away_goals = row.get('away_score', row.get('away_goals'))
        try:
            home_goals, away_goals = int(home_goals), int(away_goals)
        except (TypeError, ValueError):
            continue
        if home_goals < 0 or away_goals < 0:
            continue
        return home_goals, away_goals, source
    return None


def settle_manual_parlays(conn, now, lookup_fs, lookup_alt, lookup_espn=None, parlay_id=None, lookup_fotmob=None):
    """Settle each manual slip as one unit; leg payouts multiply, including half results.

    With parlay_id, ignore the start_ts gate and settle that single slip if every
    leg has a final score in the feeds (operator-triggered refresh).
    """
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='parlay_slips'").fetchone():
        return 0
    if parlay_id is None:
        slips = conn.execute("SELECT id FROM parlay_slips WHERE source='manual_lock' AND status='pending'").fetchall()
    else:
        slips = conn.execute("SELECT id FROM parlay_slips WHERE id=? AND status='pending'", (int(parlay_id),)).fetchall()
    count = 0
    for slip in slips:
        legs = conn.execute('SELECT * FROM parlay_legs WHERE parlay_id=? ORDER BY id', (slip['id'],)).fetchall()
        if not legs:
            continue
        if parlay_id is None and any(leg['start_ts'] > now - SETTLE_DELAY_S for leg in legs):
            continue
        outcomes = []
        for leg in legs:
            if parlay_id is None and leg['start_ts'] > now - SETTLE_DELAY_S:
                continue
            score = result_for_bet(leg['home'], leg['away'], leg['start_ts'], lookup_fs, lookup_alt, lookup_espn, lookup_fotmob)
            if not score:
                continue
            home_goals, away_goals, _ = score
            try:
                outcome = settle_bet(leg['market'], leg['pick'], leg['odds'], home_goals, away_goals)
            except (KeyError, TypeError, ValueError):
                continue
            if outcome is None:
                continue
            won, profit = outcome
            outcomes.append((leg['id'], won, profit, home_goals, away_goals))
            conn.execute('''UPDATE parlay_legs SET result=?,leg_return=?,home_score=?,away_score=?,settled_at=? WHERE id=?''',
                         ('push' if won is None else 'won' if won else 'lost', 1 + profit,
                          home_goals, away_goals, datetime.now(timezone.utc).isoformat(), leg['id']))
        if len(outcomes) != len(legs):
            continue
        gross = math.prod(1 + item[2] for item in outcomes)
        profit = round(gross - 1, 4)
        status = 'won' if profit > 0 else 'lost' if profit < 0 else 'push'
        settled_at = datetime.now(timezone.utc).isoformat()
        for leg_id, won, leg_profit, home_goals, away_goals in outcomes:
            conn.execute('''UPDATE parlay_legs SET result=?,leg_return=?,home_score=?,away_score=?,settled_at=? WHERE id=?''',
                         ('push' if won is None else 'won' if won else 'lost', 1 + leg_profit,
                          home_goals, away_goals, settled_at, leg_id))
        conn.execute('UPDATE parlay_slips SET status=?,profit=?,settled_at=? WHERE id=?',
                     (status, profit, settled_at, slip['id']))
        count += 1
    return count


def due_pending_parlays(conn, now):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='parlay_slips'").fetchone():
        return 0
    return conn.execute('''SELECT COUNT(*) FROM parlay_slips p
        WHERE p.source='manual_lock' AND p.status='pending'
          AND EXISTS (SELECT 1 FROM parlay_legs l WHERE l.parlay_id=p.id)
          AND NOT EXISTS (SELECT 1 FROM parlay_legs l WHERE l.parlay_id=p.id AND l.start_ts > ?)''',
        (now - SETTLE_DELAY_S,)).fetchone()[0]


def pending_parlay_ids(conn, now, parlay_id=None):
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'parlay_slips', 'parlay_legs'}.issubset(tables):
        return []
    if parlay_id is not None:
        rows = conn.execute("SELECT id FROM parlay_slips WHERE id=? AND source='manual_lock' AND status='pending'", (int(parlay_id),)).fetchall()
        return [row['id'] for row in rows]
    rows = conn.execute('''SELECT p.id FROM parlay_slips p
        WHERE p.source='manual_lock' AND p.status='pending'
          AND EXISTS (SELECT 1 FROM parlay_legs l WHERE l.parlay_id=p.id)
          AND NOT EXISTS (SELECT 1 FROM parlay_legs l WHERE l.parlay_id=p.id AND l.start_ts > ?)
        ORDER BY p.id''', (now - SETTLE_DELAY_S,)).fetchall()
    return [row['id'] for row in rows]


def fetch_result_feeds(target_dates, leagues, league_dates=None, required_fixtures=None):
    """Fetch only the dates and (for ESPN) competitions required by due rows."""
    feeds = {
        'flashscore': lambda: scores_flashscore.fetch_recent_results(
            days=0, use_cache=False, target_dates=target_dates),
        'fotmob': lambda: scores_fotmob.fetch_recent_results(
            days=0, use_cache=False, target_dates=target_dates),
        'espn': lambda: scores_espn.fetch_recent_results(
            days=0, use_cache=False, target_dates=target_dates, leagues=leagues,
            league_dates=league_dates),
    }
    results = {}
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        futures = {pool.submit(fetch): name for name, fetch in feeds.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
                rows = sum(len(value) for value in results[name].values()) if isinstance(results[name], dict) else len(results[name] or [])
                print(f'[settle] feed={name} rows={rows}', flush=True)
            except Exception as exc:
                results[name] = {} if name != 'espn' else []
                print(f'[settle] WARN feed={name} failed: {exc}', flush=True)
    lookup_fs = scores_flashscore.build_lookup(results.get('flashscore') or {})
    lookup_fotmob = scores_fotmob.build_lookup(results.get('fotmob') or {})
    lookup_espn = scores_espn.build_lookup(results.get('espn') or [])
    unresolved = []
    for fixture in required_fixtures or ():
        if result_for_bet(fixture['home'], fixture['away'], fixture['start_ts'],
                          lookup_fs, {}, lookup_espn, lookup_fotmob) is None:
            unresolved.append(fixture)
    if unresolved or required_fixtures is None:
        try:
            results['alt'] = scores_alt.fetch_recent_results(use_cache=False)
            row_count = sum(len(value) for value in results['alt'].values())
            print(f'[settle] feed=alt rows={row_count} fallback_fixtures={len(unresolved)}', flush=True)
        except Exception as exc:
            results['alt'] = {}
            print(f'[settle] WARN feed=alt failed: {exc}', flush=True)
    else:
        results['alt'] = {}
        print('[settle] feed=alt skipped; primary feeds covered all due fixtures', flush=True)
    return results


@serialize_settlement
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parlay-id', type=int, default=None,
                        help='force-settle one manual parlay, ignoring the start_ts gate')
    args = parser.parse_args()

    if not os.path.exists(DB_PATH):
        print(json.dumps({'status': 'error', 'message': 'bets.db missing'}))
        return 1

    now = time.time()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute('PRAGMA busy_timeout=30000')
    conn.row_factory = sqlite3.Row

    unsettled = conn.execute(
        'SELECT id, match, home, away, league, start_ts, market, pick, odds, source_match_id FROM bets WHERE settled=0 AND start_ts <= ?',
        (now - SETTLE_DELAY_S,),
    ).fetchall()

    pending_parlays = due_pending_parlays(conn, now)
    due_slip_ids = pending_parlay_ids(conn, now, args.parlay_id)
    if not unsettled and not due_slip_ids:
        conn.close()
        print(json.dumps({'status': 'ok', 'settled': 0, 'pending': 0, 'parlay_settled': 0, 'pending_parlays': 0}))
        return 0

    parlay_legs = []
    if due_slip_ids and conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='parlay_legs'").fetchone():
        marks = ','.join('?' for _ in due_slip_ids)
        parlay_legs = conn.execute(
            f'SELECT * FROM parlay_legs WHERE parlay_id IN ({marks})', due_slip_ids).fetchall()
    target_rows = [*unsettled, *parlay_legs]
    target_dates = sorted({datetime.fromtimestamp(float(row['start_ts']), timezone.utc).date().isoformat()
                           for row in target_rows if row['start_ts'] is not None})
    target_leagues = sorted({row['league'] for row in target_rows
                             if 'league' in row.keys() and row['league']})
    league_dates = sorted({(datetime.fromtimestamp(float(row['start_ts']), timezone.utc).date().isoformat(),
                            row['league'])
                           for row in target_rows
                           if row['start_ts'] is not None and 'league' in row.keys() and row['league']})
    print(f'[settle] scanning {len(unsettled)} singles, {len(due_slip_ids)} parlays '
          f'across {len(target_dates)} kickoff dates', flush=True)
    feeds = fetch_result_feeds(target_dates, target_leagues, league_dates, target_rows)
    lookup_fs_idx = scores_flashscore.build_lookup(feeds['flashscore'])
    lookup_alt_idx = scores_alt.build_lookup(feeds['alt'])
    lookup_espn_idx = scores_espn.build_lookup(feeds['espn'])
    lookup_fotmob_idx = scores_fotmob.build_lookup(feeds['fotmob'])

    settled_count = 0
    for bet in unsettled:
        result = result_for_bet(bet['home'], bet['away'], bet['start_ts'], lookup_fs_idx, lookup_alt_idx, lookup_espn_idx, lookup_fotmob_idx)
        if not result:
            continue
        home_goals, away_goals, source = result
        try:
            outcome = settle_bet(bet['market'], bet['pick'], bet['odds'], home_goals, away_goals)
        except (KeyError, TypeError, ValueError):
            continue
        if outcome is None:
            continue
        won, profit = outcome
        settled_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            'UPDATE bets SET settled=1, won=?, profit=?, settled_at=?, home_score=?, away_score=?, score_status=? WHERE id=? AND settled=0',
            (won, profit, settled_at, home_goals, away_goals, 'final', bet['id']),
        )
        settled_count += 1

    parlay_settled = settle_manual_parlays(
        conn, now, lookup_fs_idx, lookup_alt_idx, lookup_espn_idx,
        parlay_id=args.parlay_id, lookup_fotmob=lookup_fotmob_idx)
    pending_parlays = due_pending_parlays(conn, now)
    conn.commit()
    remaining = conn.execute('SELECT COUNT(*) c FROM bets WHERE settled=0').fetchone()['c']
    conn.close()

    subprocess.run([sys.executable, SNAPSHOT_SCRIPT, '--db', DB_PATH], check=True)

    print(json.dumps({
        'status': 'ok', 'settled': settled_count,
        'to_settle': len(unsettled), 'remaining': remaining,
        'parlay_settled': parlay_settled, 'pending_parlays': pending_parlays,
        'kickoff_dates_checked': target_dates,
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
