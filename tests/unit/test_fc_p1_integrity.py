from datetime import date
from pathlib import Path
import runpy
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
import scores_flashscore as fs
from football_formula_engine.fixture_matching import unique_result

settle = runpy.run_path(str(ROOT / 'scripts/fc-settle-live.py'))['settle_bet']
replay = runpy.run_path(str(ROOT / 'scripts/fc-p1-dry-run.py'))['replay']


def test_ambiguous_results_rejected_and_exact_date_preferred():
    a = dict(home='A', away='B', date_key='2026-09-25', home_goals=1, away_goals=0)
    b = dict(a, home_goals=0)
    assert unique_result([a, a], date(2026, 9, 25)) == a
    assert unique_result([a, b], date(2026, 9, 25)) is None
    assert unique_result([dict(a, date_key='2026-09-24'), a], date(2026, 9, 25)) == a
    assert unique_result([a], date(2026, 9, 27)) is None


def test_alias_and_normalization_preserve_team_identity():
    assert fs.name_keys('Paris Saint-Germain') & fs.name_keys('Paris Saint Germain')
    assert not fs.name_keys('Manchester City') & fs.name_keys('Manchester United')
    assert not fs.name_keys('Arsenal Women') & fs.name_keys('Arsenal')
    assert not fs.name_keys('Japan U20') & fs.name_keys('Japan U23')


def test_quarter_payout_precision_and_invalid_line():
    assert settle('ou', 'Over 2.25', 1.913, 1, 1) == (0, -.5)
    assert settle('ou', 'Under 2.25', 1.913, 1, 1) == (1, .4565)
    assert settle('ah', 'AH Home +0.25', 1.913, 1, 1) == (1, .4565)
    assert settle('ou', 'Over 2.26', 1.9, 1, 1) is None


def test_replay_repeatable_requires_verified_period_and_handles_bad_row():
    bet = dict(home='Example Home', away='Example Away', start_ts=1790294400,
               market='ou', pick='Under 2.25', odds=1.913, probability=.6)
    snapshot = {'overdue': [bet, dict(bet, pick='Unknown')]}
    row = dict(home=bet['home'], away=bet['away'], date_key='2026-09-25',
               home_goals=1, away_goals=1, period='90min', status='ft')
    report = replay(snapshot, [row])
    assert report == replay(snapshot, [row])
    assert report['matched'] == 1 and report['unresolved'] == 1
    assert replay(snapshot, [dict(row, period='120min')])['matched'] == 0


def test_parlay_partial_results_and_final_retry_do_not_double_count():
    import sqlite3
    namespace = runpy.run_path(str(ROOT / 'scripts/fc-settle-live.py'))
    settle_parlays = namespace['settle_manual_parlays']
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
      CREATE TABLE parlay_slips(id INTEGER,source TEXT,status TEXT,profit REAL,settled_at TEXT);
      CREATE TABLE parlay_legs(id INTEGER,parlay_id INTEGER,home TEXT,away TEXT,start_ts INTEGER,
        market TEXT,pick TEXT,odds REAL,result TEXT,leg_return REAL,home_score INTEGER,
        away_score INTEGER,settled_at TEXT);
      INSERT INTO parlay_slips VALUES(1,'manual_lock','pending',NULL,NULL);
      INSERT INTO parlay_legs VALUES(1,1,'Example Home','Example Away',1790294400,
        'ou','Under 2.25',1.913,NULL,NULL,NULL,NULL,NULL);
      INSERT INTO parlay_legs VALUES(2,1,'Other Home','Other Away',1790294400,
        '1x2','Home (Other Home)',2.0,NULL,NULL,NULL,NULL,NULL);
    ''')
    first = dict(home='Example Home',away='Example Away',date_key='2026-09-25',
                 home_goals=1,away_goals=1,period='90min',status='ft')
    lookup = fs.build_lookup({('a','b'):first})
    now = 1790500000
    assert settle_parlays(conn,now,lookup,{}) == 0
    assert conn.execute('SELECT leg_return FROM parlay_legs WHERE id=1').fetchone()[0] == pytest.approx(1.4565)
    second = dict(first,home='Other Home',away='Other Away',home_goals=2,away_goals=0)
    lookup = fs.build_lookup({('a','b'):first,('c','d'):second})
    assert settle_parlays(conn,now,lookup,{}) == 1
    profit = conn.execute('SELECT profit FROM parlay_slips').fetchone()[0]
    assert profit == pytest.approx(1.913)
    assert settle_parlays(conn,now,lookup,{}) == 0
    assert conn.execute('SELECT profit FROM parlay_slips').fetchone()[0] == profit
