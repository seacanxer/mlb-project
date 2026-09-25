#!/usr/bin/env python3
"""Write an operator-selected FC pick to the existing settlement ledger.

The server resolves every field from the latest scan. Browser payloads identify
the choice and displayed odds only; they cannot supply a score, kickoff or EV.
"""
import argparse
import hashlib
import json
import math
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FC = ROOT / 'betting-machine-fc'
MATCHES = Path(os.environ.get('FC_MATCHES_PATH', str(FC / 'matches_detailed.json')))
DB = Path(os.environ.get('FC_BETS_DB', str(FC / 'bets.db')))
MARKETS = {'1x2', 'ah', 'ou', 'btts'}
MAX_QUOTE_AGE = 600


def fail(message):
    print(json.dumps({'status': 'error', 'message': message}))
    return 1


def create(match_id, market, pick_name, expected_odds):
    now = time.time()
    if market not in MARKETS or not match_id or not pick_name or expected_odds is None or not math.isfinite(expected_odds):
        return fail('Pilihan tidak valid.')
    try:
        matches = json.loads(MATCHES.read_text(encoding='utf-8'))
        match = next(m for m in matches if str(m.get('info', {}).get('match_id')) == match_id)
        info = match['info']
        kickoff = int(float(info['start_ts']))
        if kickoff <= now + 60:
            return fail('Kickoff sudah terlalu dekat atau lewat; lock ditolak.')
        candidates = match.get('market_options') or match.get('projections') or []
        choice = next(p for p in candidates if p.get('market') == market and p.get('pick') == pick_name)
        odds = float(choice['odds'])
        if not math.isfinite(odds) or odds <= 1 or abs(odds - expected_odds) > 0.0001:
            return fail('Odds sudah berubah. Muat ulang pertandingan sebelum lock.')
        captured = float(choice.get('quote_captured_at') or match.get('analysis', {}).get('quote_captured_at') or 0)
        if captured <= 0 or captured > now + 5 or now - captured > MAX_QUOTE_AGE:
            return fail('Odds scan sudah kedaluwarsa. Jalankan Perbarui analisis sebelum lock.')
        probability = float(choice.get('probability') or 0)
        ev = float(choice.get('ev') or 0)
        if not 0 <= probability <= 1 or not math.isfinite(ev):
            return fail('Data model tidak valid untuk settlement.')
    except (OSError, ValueError, KeyError, StopIteration, TypeError):
        return fail('Pilihan tidak ditemukan pada scan terbaru.')

    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('''CREATE TABLE IF NOT EXISTS manual_locks (
            bet_id INTEGER PRIMARY KEY REFERENCES bets(id),
            source_match_id TEXT NOT NULL,
            market TEXT NOT NULL,
            pick TEXT NOT NULL,
            locked_at TEXT NOT NULL,
            formula_version TEXT,
            snapshot TEXT,
            UNIQUE(source_match_id, market)
        )''')
        if 'snapshot' not in {row[1] for row in conn.execute('PRAGMA table_info(manual_locks)')}:
            conn.execute('ALTER TABLE manual_locks ADD COLUMN snapshot TEXT')
        existing = conn.execute(
            'SELECT bet_id,pick,locked_at FROM manual_locks WHERE source_match_id=? AND market=?',
            (match_id, market)).fetchone()
        if existing:
            conn.commit()
            if existing['pick'] != pick_name:
                return fail('Market pertandingan ini sudah dikunci dengan pilihan lain.')
            print(json.dumps({'status': 'locked', 'bet_id': existing['bet_id'],
                              'locked_at': existing['locked_at'], 'already_locked': True}))
            return 0
        locked_at = datetime.fromtimestamp(now, timezone.utc).isoformat()
        cur = conn.execute('''INSERT INTO bets
            (match,home,away,league,start_ts,market,pick,odds,ev,probability,
             placed_at,settled,won,profit,settled_at,source_match_id,
             home_score,away_score,score_status,score_updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (f"{info['home']} vs {info['away']}", info['home'], info['away'],
             info.get('league') or '', kickoff, market, pick_name, odds, ev,
             probability, locked_at, 0, None, None, None, match_id,
             None, None, None, None))
        bet_id = cur.lastrowid
        conn.execute('''INSERT INTO manual_locks
            (bet_id,source_match_id,market,pick,locked_at,formula_version,snapshot)
            VALUES (?,?,?,?,?,?,?)''',
            (bet_id, match_id, market, pick_name, locked_at,
             choice.get('formula_version') or match.get('analysis', {}).get('formula_version'),
             json.dumps({'match': {'info': info}, 'pick': choice}, ensure_ascii=False)))
        conn.commit()
    except sqlite3.Error as exc:
        if conn.in_transaction:
            conn.rollback()
        return fail(f'Ledger tidak dapat ditulis: {exc}')
    finally:
        conn.close()
    try:
        subprocess.run([sys.executable, str(ROOT / 'scripts' / 'fc-snapshot.py'),
                        '--db', str(DB), '--out', os.environ.get('FC_TRACKER_OUT', str(FC / 'tracker_snapshot.json'))],
                       cwd=ROOT, check=True, capture_output=True)
        snapshot_status = 'updated'
    except subprocess.CalledProcessError:
        snapshot_status = 'pending_refresh'
    print(json.dumps({'status': 'locked', 'bet_id': bet_id, 'already_locked': False,
                      'locked_at': locked_at, 'odds': odds, 'snapshot_status': snapshot_status}))
    return 0


def list_locks():
    if not DB.exists():
        print(json.dumps({'status': 'ok', 'locks': []}))
        return 0
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='manual_locks'").fetchone()
        if exists and 'snapshot' not in {row[1] for row in conn.execute('PRAGMA table_info(manual_locks)')}:
            conn.execute('ALTER TABLE manual_locks ADD COLUMN snapshot TEXT')
        rows = [] if not exists else [dict(row) for row in conn.execute('''
            SELECT b.id AS bet_id,b.source_match_id,b.match,b.home,b.away,b.league,
                   b.start_ts,b.market,b.pick,b.odds,b.probability,b.ev,b.settled,
                   m.locked_at,m.formula_version,m.snapshot
            FROM manual_locks m JOIN bets b ON b.id=m.bet_id
            ORDER BY m.locked_at DESC''')]
        locks = []
        for row in rows:
            snapshot = json.loads(row['snapshot']) if row['snapshot'] else {
                'match': {'info': {'match_id': row['source_match_id'], 'home': row['home'],
                                   'away': row['away'], 'league': row['league'],
                                   'start_ts': row['start_ts']}},
                'pick': {'market': row['market'], 'pick': row['pick'], 'odds': row['odds'],
                         'probability': row['probability'], 'ev': row['ev']}}
            locks.append({**snapshot, 'id': f"{row['source_match_id']}|{row['market']}|{row['pick']}",
                          'lockedAt': row['locked_at'], 'settlementId': row['bet_id'],
                          'settled': bool(row['settled'])})
        slips = []
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='parlay_slips'").fetchone():
            for slip in conn.execute("SELECT id,combined_odds,generated_at,status,profit FROM parlay_slips WHERE source='manual_lock' ORDER BY id DESC"):
                legs = [dict(leg) for leg in conn.execute(
                    'SELECT source_match_id,home,away,market,pick,odds,result FROM parlay_legs WHERE parlay_id=? ORDER BY id', (slip['id'],))]
                slips.append({'id': slip['id'], 'odds': slip['combined_odds'], 'lockedAt': slip['generated_at'],
                              'status': slip['status'], 'profit': slip['profit'], 'legs': legs})
        print(json.dumps({'status': 'ok', 'locks': locks, 'parlays': slips}))
        return 0
    finally:
        conn.close()


def batch_lock(payload):
    """Validate all selections first, then commit one atomic singles batch or parlay."""
    mode = payload.get('mode')
    requested = payload.get('choices')
    if mode not in ('singles', 'parlay') or not isinstance(requested, list) or not 1 <= len(requested) <= 30:
        return fail('Batch harus berisi 1–30 pilihan dan mode singles/parlay.')
    if mode == 'parlay' and len(requested) < 2:
        return fail('Parlay membutuhkan sedikitnya dua pilihan.')
    now = time.time()
    try:
        matches = json.loads(MATCHES.read_text(encoding='utf-8'))
        index = {str(m.get('info', {}).get('match_id')): m for m in matches}
        validated = []
        seen = set()
        for item in requested:
            match_id, market, pick_name = str(item['match_id']), item['market'], item['pick']
            expected_odds = float(item['odds'])
            if market not in MARKETS or not match_id or not pick_name or not math.isfinite(expected_odds):
                raise ValueError('Pilihan tidak valid.')
            key = (match_id, market)
            if key in seen:
                raise ValueError('Satu market pada pertandingan yang sama hanya boleh dipilih sekali.')
            seen.add(key)
            match = index[match_id]
            info = match['info']
            kickoff = int(float(info['start_ts']))
            if kickoff <= now + 60:
                raise ValueError('Kickoff sudah terlalu dekat atau lewat; lock ditolak.')
            candidates = match.get('market_options') or match.get('projections') or []
            choice = next(p for p in candidates if p.get('market') == market and p.get('pick') == pick_name)
            odds = float(choice['odds'])
            if not math.isfinite(odds) or odds <= 1 or abs(odds - expected_odds) > 0.0001:
                raise ValueError('Odds sudah berubah. Muat ulang pertandingan sebelum lock.')
            captured = float(choice.get('quote_captured_at') or match.get('analysis', {}).get('quote_captured_at') or 0)
            if captured <= 0 or captured > now + 5 or now - captured > MAX_QUOTE_AGE:
                raise ValueError('Odds scan sudah kedaluwarsa. Jalankan Perbarui analisis sebelum lock.')
            probability, ev = float(choice.get('probability') or 0), float(choice.get('ev') or 0)
            if not 0 <= probability <= 1 or not math.isfinite(ev):
                raise ValueError('Data model tidak valid untuk settlement.')
            validated.append((match_id, market, pick_name, info, choice, kickoff, odds, probability, ev))
    except (OSError, KeyError, TypeError, StopIteration, ValueError) as exc:
        return fail(str(exc) if isinstance(exc, ValueError) and str(exc) else 'Pilihan tidak ditemukan pada scan terbaru.')

    locked_at = datetime.fromtimestamp(now, timezone.utc).isoformat()
    conn = sqlite3.connect(DB, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('BEGIN IMMEDIATE')
        if mode == 'singles':
            conn.execute('''CREATE TABLE IF NOT EXISTS manual_locks (
                bet_id INTEGER PRIMARY KEY REFERENCES bets(id), source_match_id TEXT NOT NULL,
                market TEXT NOT NULL, pick TEXT NOT NULL, locked_at TEXT NOT NULL,
                formula_version TEXT, snapshot TEXT, UNIQUE(source_match_id, market))''')
            if 'snapshot' not in {row[1] for row in conn.execute('PRAGMA table_info(manual_locks)')}:
                conn.execute('ALTER TABLE manual_locks ADD COLUMN snapshot TEXT')
            conflicts = [v for v in validated if (row := conn.execute(
                'SELECT pick FROM manual_locks WHERE source_match_id=? AND market=?', (v[0], v[1])).fetchone()) and row['pick'] != v[2]]
            if conflicts:
                raise ValueError('Ada market yang sudah dikunci dengan pilihan lain. Tidak ada batch yang disimpan.')
            locks = []
            for match_id, market, pick_name, info, choice, kickoff, odds, probability, ev in validated:
                existing = conn.execute('SELECT bet_id,locked_at FROM manual_locks WHERE source_match_id=? AND market=?', (match_id, market)).fetchone()
                if existing:
                    bet_id, item_time = existing['bet_id'], existing['locked_at']
                else:
                    cur = conn.execute('''INSERT INTO bets
                        (match,home,away,league,start_ts,market,pick,odds,ev,probability,
                         placed_at,settled,won,profit,settled_at,source_match_id,
                         home_score,away_score,score_status,score_updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (f"{info['home']} vs {info['away']}", info['home'], info['away'], info.get('league') or '',
                         kickoff, market, pick_name, odds, ev, probability, locked_at, 0, None, None, None,
                         match_id, None, None, None, None))
                    bet_id, item_time = cur.lastrowid, locked_at
                    conn.execute('''INSERT INTO manual_locks
                        (bet_id,source_match_id,market,pick,locked_at,formula_version,snapshot) VALUES (?,?,?,?,?,?,?)''',
                        (bet_id, match_id, market, pick_name, locked_at,
                         choice.get('formula_version'), json.dumps({'match': {'info': info}, 'pick': choice}, ensure_ascii=False)))
                locks.append({'id': f'{match_id}|{market}|{pick_name}', 'bet_id': bet_id, 'locked_at': item_time})
            result = {'status': 'locked', 'mode': mode, 'locks': locks}
        else:
            conn.execute('''CREATE TABLE IF NOT EXISTS parlay_slips (
                id INTEGER PRIMARY KEY, generation_key TEXT, fingerprint TEXT UNIQUE, tier TEXT,
                label TEXT, source TEXT, combined_odds REAL, model_joint_probability REAL,
                generated_at TEXT, status TEXT DEFAULT 'pending', profit REAL, settled_at TEXT,
                match_signature TEXT)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS parlay_legs (
                id INTEGER PRIMARY KEY, parlay_id INTEGER NOT NULL, candidate_id TEXT,
                source_match_id TEXT, match TEXT, home TEXT, away TEXT, league TEXT,
                start_ts INTEGER, market TEXT, pick TEXT, odds REAL, result TEXT DEFAULT 'pending',
                leg_return REAL, home_score INTEGER, away_score INTEGER, settled_at TEXT)''')
            fingerprint = hashlib.sha256(json.dumps(sorted((v[0], v[1], v[2], v[6]) for v in validated)).encode()).hexdigest()
            existing = conn.execute("SELECT id,combined_odds,generated_at FROM parlay_slips WHERE fingerprint=? AND source='manual_lock'", (fingerprint,)).fetchone()
            if existing:
                slip_id, combined, item_time = existing['id'], existing['combined_odds'], existing['generated_at']
            else:
                combined = math.prod(v[6] for v in validated)
                cur = conn.execute('''INSERT INTO parlay_slips
                    (generation_key,fingerprint,tier,label,source,combined_odds,generated_at,status,match_signature)
                    VALUES (?,?,?,?,?,?,?,?,?)''',
                    (locked_at, fingerprint, 'manual', 'Operator parlay', 'manual_lock', combined, locked_at,
                     'pending', ','.join(sorted({v[0] for v in validated}))))
                slip_id, item_time = cur.lastrowid, locked_at
                for match_id, market, pick_name, info, choice, kickoff, odds, _, _ in validated:
                    conn.execute('''INSERT INTO parlay_legs
                        (parlay_id,candidate_id,source_match_id,match,home,away,league,start_ts,market,pick,odds,result)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (slip_id, f'{match_id}|{market}|{pick_name}', match_id,
                         f"{info['home']} vs {info['away']}", info['home'], info['away'],
                         info.get('league') or '', kickoff, market, pick_name, odds, 'pending'))
            result = {'status': 'locked', 'mode': mode, 'parlay_id': slip_id, 'odds': combined,
                      'locked_at': item_time, 'already_locked': bool(existing)}
        conn.commit()
    except (sqlite3.Error, ValueError) as exc:
        if conn.in_transaction:
            conn.rollback()
        return fail(str(exc))
    finally:
        conn.close()
    try:
        subprocess.run([sys.executable, str(ROOT / 'scripts' / 'fc-snapshot.py'), '--db', str(DB),
                        '--out', os.environ.get('FC_TRACKER_OUT', str(FC / 'tracker_snapshot.json'))],
                       cwd=ROOT, check=True, capture_output=True)
    except subprocess.CalledProcessError:
        result['snapshot_status'] = 'pending_refresh'
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['create', 'list', 'batch'])
    ap.add_argument('--match-id')
    ap.add_argument('--market')
    ap.add_argument('--pick')
    ap.add_argument('--odds', type=float)
    ap.add_argument('--payload')
    args = ap.parse_args()
    raise SystemExit(create(args.match_id, args.market, args.pick, args.odds)
                     if args.action == 'create' else list_locks() if args.action == 'list'
                     else batch_lock(json.loads(args.payload or '{}')))
