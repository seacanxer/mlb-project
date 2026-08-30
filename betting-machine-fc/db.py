import os
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('FC_BETS_DB', os.path.join(BASE_DIR, 'bets.db'))


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = _connect()
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
    columns = {row['name'] for row in c.execute('PRAGMA table_info(bets)').fetchall()}
    if 'source_match_id' not in columns:
        c.execute('ALTER TABLE bets ADD COLUMN source_match_id TEXT')
    conn.commit()
    conn.close()

def insert_bet(bet):
    """Lock one recommendation per fixture. If an unsettled lock already exists
    for the same match+start_ts, keep the higher EV. If it is already settled,
    skip entirely so scans never stack duplicates."""
    conn = _connect()
    c = conn.cursor()
    existing = c.execute('''
        SELECT id, ev, settled FROM bets
        WHERE (
            (? IS NOT NULL AND source_match_id=?)
            OR (
                LOWER(TRIM(match))=LOWER(TRIM(?))
                AND start_ts IS NOT NULL
                AND date(start_ts, 'unixepoch')=date(?, 'unixepoch')
            )
        )
        ORDER BY settled DESC, ev DESC
        LIMIT 1
    ''', (
        str(bet.get('match_id')) if bet.get('match_id') is not None else None,
        str(bet.get('match_id')) if bet.get('match_id') is not None else None,
        bet.get('match'), bet.get('start_ts'),
    )).fetchone()
    if existing:
        if existing['settled']:
            conn.close()
            return existing['id'], False
        new_ev = bet.get('ev') or -999
        if new_ev > (existing['ev'] or -999):
            c.execute('''
                UPDATE bets
                SET market=?, pick=?, odds=?, ev=?, probability=?, placed_at=?,
                    source_match_id=COALESCE(?, source_match_id)
                WHERE id=?
            ''', (
                bet.get('market'), bet.get('pick'), bet.get('odds'),
                bet.get('ev'), bet.get('probability'),
                datetime.now().isoformat(),
                str(bet.get('match_id')) if bet.get('match_id') is not None else None,
                existing['id']
            ))
            conn.commit()
            conn.close()
            return existing['id'], False
        conn.close()
        return existing['id'], False
    c.execute('''
        INSERT INTO bets (match, home, away, league, start_ts, market, pick, odds, ev, probability, placed_at, source_match_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        datetime.now().isoformat(),
        str(bet.get('match_id')) if bet.get('match_id') is not None else None
    ))
    bet_id = c.lastrowid
    conn.commit()
    conn.close()
    return bet_id, True

def update_source_match_id(bet_id, source_match_id):
    conn = _connect()
    c = conn.cursor()
    c.execute('UPDATE bets SET source_match_id=? WHERE id=?', (source_match_id, bet_id))
    conn.commit()
    conn.close()

def settle_bet(bet_id, won, profit):
    conn = _connect()
    c = conn.cursor()
    c.execute('''
        UPDATE bets SET settled=1, won=?, profit=?, settled_at=?
        WHERE id=?
    ''', (None if won is None else (1 if won else 0), profit, datetime.now().isoformat(), bet_id))
    conn.commit()
    conn.close()


_CANONICAL_BETS_CTE = '''
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


def get_bets(settled=None):
    """Return one canonical row for each identical locked selection.

    Historical duplicate rows remain untouched in SQLite for auditability, but
    Tracker and ROI consumers no longer display or count them more than once.
    A settled copy wins over an otherwise identical pending copy.
    """
    conn = _connect()
    c = conn.cursor()
    if settled is None:
        c.execute(_CANONICAL_BETS_CTE + '''
            SELECT * FROM ranked_bets
            WHERE duplicate_rank=1
            ORDER BY start_ts DESC, id ASC
        ''')
    else:
        c.execute(_CANONICAL_BETS_CTE + '''
            SELECT * FROM ranked_bets
            WHERE duplicate_rank=1 AND settled=?
            ORDER BY start_ts DESC, id ASC
        ''', (1 if settled else 0,))
    rows = c.fetchall()
    conn.close()
    keys = ['id','match','home','away','league','start_ts','market','pick','odds','ev','probability','placed_at','settled','won','profit','settled_at','source_match_id']
    return [dict(zip(keys, tuple(r))) for r in rows]

def get_roi():
    conn = _connect()
    c = conn.cursor()
    c.execute(_CANONICAL_BETS_CTE + '''
        SELECT COUNT(*),
               COALESCE(SUM(CASE WHEN won=1 THEN 1 ELSE 0 END), 0),
               COALESCE(SUM(CASE WHEN won=0 THEN 1 ELSE 0 END), 0),
               COALESCE(SUM(CASE WHEN won IS NULL THEN 1 ELSE 0 END), 0),
               COALESCE(SUM(profit), 0)
        FROM ranked_bets WHERE duplicate_rank=1 AND settled=1
    ''')
    total, wins, losses, pushes, profit = tuple(c.fetchone())
    conn.close()
    total = total or 0
    wins = wins or 0
    profit = profit or 0.0
    conn = _connect()
    pending_count = conn.execute(_CANONICAL_BETS_CTE + '''
        SELECT COUNT(*) FROM ranked_bets
        WHERE duplicate_rank=1 AND settled=0
    ''').fetchone()[0]
    conn.close()
    roi = (profit / total * 100) if total > 0 else 0.0
    decided = wins + losses
    hit_rate = (wins / decided * 100) if decided > 0 else 0.0
    return {
        'locked_picks': pending_count,
        'settled_picks': total,
        'wins': wins,
        'losses': losses,
        'pushes': pushes,
        'profit_units': round(profit, 2),
        'roi_pct': round(roi, 2),
        'hit_rate_pct': round(hit_rate, 2),
        'duplicates_hidden': get_duplicate_count(),
    }


def get_duplicate_count():
    conn = _connect()
    count = conn.execute(_CANONICAL_BETS_CTE + '''
        SELECT COUNT(*) FROM ranked_bets WHERE duplicate_rank > 1
    ''').fetchone()[0]
    conn.close()
    return count or 0


def get_market_performance():
    conn = _connect()
    rows = conn.execute(_CANONICAL_BETS_CTE + '''
        SELECT market,
               COUNT(*) AS bets,
               SUM(CASE WHEN won=1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN won=0 THEN 1 ELSE 0 END) AS losses,
               SUM(CASE WHEN won IS NULL THEN 1 ELSE 0 END) AS pushes,
               COALESCE(SUM(profit), 0) AS profit
        FROM ranked_bets
        WHERE duplicate_rank=1 AND settled=1
        GROUP BY market
        ORDER BY market
    ''').fetchall()
    conn.close()
    result = []
    for row in rows:
        bets = row['bets'] or 0
        wins = row['wins'] or 0
        losses = row['losses'] or 0
        decided = wins + losses
        profit = float(row['profit'] or 0.0)
        result.append({
            'market': row['market'] or 'unknown',
            'bets': bets,
            'wins': wins,
            'losses': losses,
            'pushes': row['pushes'] or 0,
            'win_rate_pct': round(wins / decided * 100, 2) if decided else 0.0,
            'loss_rate_pct': round(losses / decided * 100, 2) if decided else 0.0,
            'profit_units': round(profit, 2),
            'roi_pct': round(profit / bets * 100, 2) if bets else 0.0,
        })
    return result

def get_unsettled():
    return get_bets(settled=False)

def get_settled():
    return get_bets(settled=True)
