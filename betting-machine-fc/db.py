import sqlite3
import json
from datetime import datetime

DB_PATH = '/home/ubuntu/mlb-project/betting-machine-fc/bets.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match TEXT,
            home TEXT,
            away TEXT,
            league TEXT,
            start_ts INTEGER,
            market TEXT,
            pick TEXT,
            odds REAL,
            ev REAL,
            probability REAL,
            placed_at TEXT,
            settled INTEGER DEFAULT 0,
            won INTEGER DEFAULT 0,
            profit REAL DEFAULT 0.0,
            settled_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

def insert_bet(bet):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO bets (match, home, away, league, start_ts, market, pick, odds, ev, probability, placed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        bet.get('match'),
        bet.get('home'),
        bet.get('away'),
        bet.get('league'),
        bet.get('start_ts'),
        bet.get('market'),
        bet.get('pick'),
        bet.get('odds'),
        bet.get('ev'),
        bet.get('probability'),
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()

def settle_bet(bet_id, won, profit):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        UPDATE bets SET settled=1, won=?, profit=?, settled_at=?
        WHERE id=?
    ''', (1 if won else 0, profit, datetime.now().isoformat(), bet_id))
    conn.commit()
    conn.close()

def get_bets(settled=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if settled is None:
        c.execute('SELECT * FROM bets ORDER BY start_ts DESC')
    else:
        c.execute('SELECT * FROM bets WHERE settled=? ORDER BY start_ts DESC', (1 if settled else 0,))
    rows = c.fetchall()
    conn.close()
    keys = ['id','match','home','away','league','start_ts','market','pick','odds','ev','probability','placed_at','settled','won','profit','settled_at']
    return [dict(zip(keys, r)) for r in rows]

def get_roi():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT COUNT(*), SUM(won), SUM(profit) FROM bets WHERE settled=1')
    total, wins, profit = c.fetchone()
    conn.close()
    total = total or 0
    wins = wins or 0
    profit = profit or 0.0
    roi = (profit / total * 100) if total > 0 else 0.0
    hit_rate = (wins / total * 100) if total > 0 else 0.0
    return {'total_bets': total, 'wins': wins, 'profit': round(profit, 2), 'roi_pct': round(roi, 2), 'hit_rate_pct': round(hit_rate, 2)}

def get_unsettled():
    return get_bets(settled=False)

def get_settled():
    return get_bets(settled=True)