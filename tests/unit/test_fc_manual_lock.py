"""Manual FC locks must enter the same bets ledger used by settlement."""
import json
import os
import runpy
import sqlite3
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts' / 'fc-manual-lock.py'


def run_lock(tmp_path, *, quote_age=30, odds=1.91):
    now = time.time()
    fixture = {
        'info': {'match_id': 'fixture-1', 'home': 'Home', 'away': 'Away',
                 'league': 'Example League', 'start_ts': now + 7200},
        'analysis': {'quote_captured_at': now - quote_age},
        'market_options': [{'market': 'ou', 'pick': 'Over 2.5', 'odds': odds,
                            'probability': 0.57, 'ev': 0.08,
                            'quote_captured_at': now - quote_age,
                            'formula_version': 'test-v1'}],
    }
    matches = tmp_path / 'matches.json'
    matches.write_text(json.dumps([fixture]), encoding='utf-8')
    db = tmp_path / 'bets.db'
    conn = sqlite3.connect(db)
    conn.execute('''CREATE TABLE bets (
        id INTEGER PRIMARY KEY AUTOINCREMENT, match TEXT, home TEXT, away TEXT,
        league TEXT, start_ts INTEGER, market TEXT, pick TEXT, odds REAL,
        ev REAL, probability REAL, placed_at TEXT, settled INTEGER, won INTEGER,
        profit REAL, settled_at TEXT, source_match_id TEXT, home_score INTEGER,
        away_score INTEGER, score_status TEXT, score_updated_at TEXT)''')
    conn.commit()
    conn.close()
    env = {**os.environ, 'FC_MATCHES_PATH': str(matches), 'FC_BETS_DB': str(db),
           'FC_TRACKER_OUT': str(tmp_path / 'tracker.json')}
    command = [sys.executable, str(SCRIPT), 'create', '--match-id', 'fixture-1',
               '--market', 'ou', '--pick', 'Over 2.5', '--odds', str(odds)]
    return db, env, command


def test_manual_lock_is_idempotent_and_enters_tracker(tmp_path):
    db, env, command = run_lock(tmp_path)
    first = subprocess.run(command, env=env, capture_output=True, text=True, check=True)
    second = subprocess.run(command, env=env, capture_output=True, text=True, check=True)
    assert json.loads(first.stdout)['status'] == 'locked'
    assert json.loads(first.stdout)['snapshot_status'] == 'updated', first.stdout
    assert json.loads(second.stdout)['already_locked'] is True
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT COUNT(*) FROM bets').fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM manual_locks').fetchone()[0] == 1
        assert conn.execute('SELECT odds FROM bets').fetchone()[0] == 1.91
    snapshot = json.loads((tmp_path / 'tracker.json').read_text(encoding='utf-8'))
    assert snapshot['summary']['manual_locked_picks'] == 1
    assert snapshot['locked'][0]['lock_source'] == 'manual'


def test_stale_quote_cannot_enter_settlement(tmp_path):
    db, env, command = run_lock(tmp_path, quote_age=1800)
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'kedaluwarsa' in json.loads(result.stdout)['message']
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT COUNT(*) FROM bets').fetchone()[0] == 0


def test_manual_lock_takes_priority_over_legacy_auto_duplicate(tmp_path):
    db, env, command = run_lock(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute('''INSERT INTO bets
            (match,home,away,league,start_ts,market,pick,odds,ev,probability,
             placed_at,settled,source_match_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            ('Home vs Away', 'Home', 'Away', 'Example League',
             int(time.time()) + 7200, 'ou', 'Over 2.5', 1.7, 0.01, 0.57,
             '2026-09-25T00:00:00+00:00', 0, 'fixture-1'))
        conn.commit()
    subprocess.run(command, env=env, capture_output=True, text=True, check=True)
    snapshot = json.loads((tmp_path / 'tracker.json').read_text(encoding='utf-8'))
    assert len(snapshot['locked']) == 1
    assert snapshot['locked'][0]['odds'] == 1.91
    assert snapshot['locked'][0]['lock_source'] == 'manual'
    assert snapshot['summary']['duplicates_hidden'] == 1


def test_settlement_counts_push_and_quarter_handicap_correctly():
    settle = runpy.run_path(str(ROOT / 'scripts' / 'fc-settle-live.py'))['settle_bet']
    assert settle('ou', 'Over 2.0', 1.9, 2, 0) == (None, 0.0)
    assert settle('ah', 'AH Away +0.25', 1.9, 1, 1) == (1, 0.45)
    assert settle('ah', 'AH Home -0.25', 1.9, 1, 1) == (0, -0.5)
