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
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
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
        if 'home_score' not in columns:
            c.execute('ALTER TABLE bets ADD COLUMN home_score INTEGER')
        if 'away_score' not in columns:
            c.execute('ALTER TABLE bets ADD COLUMN away_score INTEGER')
        if 'score_status' not in columns:
            c.execute('ALTER TABLE bets ADD COLUMN score_status TEXT')
        if 'score_updated_at' not in columns:
            c.execute('ALTER TABLE bets ADD COLUMN score_updated_at TEXT')
        c.execute('''
            CREATE TABLE IF NOT EXISTS parlay_slips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                generation_key TEXT UNIQUE,
                fingerprint TEXT,
                tier TEXT,
                label TEXT,
                source TEXT,
                combined_odds REAL,
                model_joint_probability REAL,
                generated_at TEXT,
                status TEXT DEFAULT 'pending',
                profit REAL,
                settled_at TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS parlay_legs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parlay_id INTEGER NOT NULL,
                candidate_id TEXT,
                source_match_id TEXT,
                match TEXT,
                home TEXT,
                away TEXT,
                league TEXT,
                start_ts INTEGER,
                market TEXT,
                pick TEXT,
                odds REAL,
                result TEXT DEFAULT 'pending',
                leg_return REAL,
                home_score INTEGER,
                away_score INTEGER,
                settled_at TEXT,
                FOREIGN KEY(parlay_id) REFERENCES parlay_slips(id) ON DELETE CASCADE
            )
        ''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_parlay_legs_status ON parlay_legs(result, start_ts)')
        conn.commit()


def insert_parlay_batch(payload, source='framework'):
    """Persist ready slips once per input fingerprint, source, and tier."""
    now = datetime.now().isoformat()
    created = []
    conn = _connect()
    try:
        conn.execute('PRAGMA foreign_keys=ON')
        for slip in payload.get('slips', []):
            if slip.get('status') not in {'ready', 'ready_with_fallback'}:
                continue
            tier = slip.get('tier')
            slip_source = slip.get('source') or source
            generation_key = f"{payload.get('fingerprint')}|{slip_source}|{tier}"
            cursor = conn.execute('''
                INSERT OR IGNORE INTO parlay_slips
                (generation_key, fingerprint, tier, label, source, combined_odds,
                 model_joint_probability, generated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (generation_key, payload.get('fingerprint'), tier, slip.get('label'), slip_source,
                  slip.get('combined_odds'), slip.get('model_joint_probability'), now))
            if not cursor.rowcount:
                row = conn.execute('SELECT id FROM parlay_slips WHERE generation_key=?', (generation_key,)).fetchone()
                created.append({'id': row['id'], 'tier': tier, 'created': False})
                continue
            parlay_id = cursor.lastrowid
            for leg in slip.get('legs', []):
                conn.execute('''
                    INSERT INTO parlay_legs
                    (parlay_id, candidate_id, source_match_id, match, home, away, league,
                     start_ts, market, pick, odds)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (parlay_id, leg.get('id'), str(leg.get('match_id') or ''), leg.get('match'),
                      leg.get('home'), leg.get('away'), leg.get('league'), leg.get('start_ts'),
                      leg.get('market'), leg.get('pick'), leg.get('odds')))
            created.append({'id': parlay_id, 'tier': tier, 'created': True})
        conn.commit()
    finally:
        conn.close()
    return created


def get_parlay_slips(limit=100):
    conn = _connect()
    slips = [dict(row) for row in conn.execute(
        'SELECT * FROM parlay_slips ORDER BY generated_at DESC, id DESC LIMIT ?', (limit,)
    ).fetchall()]
    for slip in slips:
        slip['legs'] = [dict(row) for row in conn.execute(
            'SELECT * FROM parlay_legs WHERE parlay_id=? ORDER BY id', (slip['id'],)
        ).fetchall()]
        slip['leg_count'] = len(slip['legs'])
    conn.close()
    return slips


def get_pending_parlay_legs():
    conn = _connect()
    rows = conn.execute('''
        SELECT l.* FROM parlay_legs l JOIN parlay_slips s ON s.id=l.parlay_id
        WHERE s.status='pending' AND l.result='pending' ORDER BY l.start_ts
    ''').fetchall()
    conn.close()
    return [dict(row) for row in rows]


def settle_parlay_leg(leg_id, result, leg_return, home_score, away_score):
    now = datetime.now().isoformat()
    conn = _connect()
    row = conn.execute('SELECT parlay_id FROM parlay_legs WHERE id=?', (leg_id,)).fetchone()
    if not row:
        conn.close()
        return
    parlay_id = row['parlay_id']
    conn.execute('''UPDATE parlay_legs SET result=?, leg_return=?, home_score=?, away_score=?, settled_at=? WHERE id=?''',
                 (result, leg_return, home_score, away_score, now, leg_id))
    legs = conn.execute('SELECT result, leg_return FROM parlay_legs WHERE parlay_id=?', (parlay_id,)).fetchall()
    if legs and all(leg['result'] != 'pending' for leg in legs):
        total_return = 1.0
        for leg in legs:
            total_return *= float(leg['leg_return'])
        profit = total_return - 1.0
        status = 'won' if profit > 1e-9 else ('lost' if profit < -1e-9 else 'push')
        conn.execute('UPDATE parlay_slips SET status=?, profit=?, settled_at=? WHERE id=?',
                     (status, profit, now, parlay_id))
    conn.commit()
    conn.close()


def get_parlay_roi():
    conn = _connect()
    row = conn.execute('''
        SELECT COUNT(*) AS settled,
               SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END) AS losses,
               SUM(CASE WHEN status='push' THEN 1 ELSE 0 END) AS pushes,
               COALESCE(SUM(profit), 0) AS profit
        FROM parlay_slips WHERE status!='pending'
    ''').fetchone()
    pending = conn.execute("SELECT COUNT(*) FROM parlay_slips WHERE status='pending'").fetchone()[0]
    conn.close()
    settled = row['settled'] or 0
    profit = float(row['profit'] or 0)
    return {'pending': pending, 'settled': settled, 'wins': row['wins'] or 0,
            'losses': row['losses'] or 0, 'pushes': row['pushes'] or 0,
            'profit_units': round(profit, 2),
            'roi_pct': round(profit / settled * 100, 2) if settled else 0.0}

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

def settle_bet(bet_id, won, profit, home_score=None, away_score=None, score_status='final'):
    conn = _connect()
    c = conn.cursor()
    c.execute('''
        UPDATE bets SET settled=1, won=?, profit=?, settled_at=?,
            home_score=COALESCE(?, home_score), away_score=COALESCE(?, away_score),
            score_status=CASE WHEN ? IS NOT NULL THEN ? ELSE score_status END,
            score_updated_at=CASE WHEN ? IS NOT NULL AND ? IS NOT NULL THEN ? ELSE score_updated_at END
        WHERE id=?
    ''', (
        None if won is None else (1 if won else 0), profit, datetime.now().isoformat(),
        home_score, away_score, score_status, score_status,
        home_score, away_score, datetime.now().isoformat(), bet_id,
    ))
    conn.commit()
    conn.close()


def reset_bet(bet_id):
    conn = _connect()
    c = conn.cursor()
    c.execute('''UPDATE bets SET settled=0, won=NULL, profit=NULL, settled_at=NULL,
        home_score=NULL, away_score=NULL, score_status=NULL, score_updated_at=NULL
        WHERE id=?''', (bet_id,))
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
    keys = ['id','match','home','away','league','start_ts','market','pick','odds','ev','probability','placed_at','settled','won','profit','settled_at','source_match_id','home_score','away_score','score_status','score_updated_at']
    return [dict(zip(keys, tuple(r))) for r in rows]

def get_roi():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
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
        # single-connection pending count
        pending_count = conn.execute(_CANONICAL_BETS_CTE + '''
            SELECT COUNT(*) FROM ranked_bets
            WHERE duplicate_rank=1 AND settled=0
        ''').fetchone()[0]
    total = total or 0
    wins = wins or 0
    profit = profit or 0.0
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

def get_stuck_bets():
    import time
    conn = _connect()
    now = time.time()
    cutoff = now - 6300
    c = conn.cursor()
    c.execute(_CANONICAL_BETS_CTE + '''
        SELECT * FROM ranked_bets
        WHERE duplicate_rank=1 AND settled=0
          AND start_ts IS NOT NULL AND start_ts < ?
        ORDER BY start_ts ASC
    ''', (cutoff,))
    rows = c.fetchall()
    conn.close()
    keys = ['id','match','home','away','league','start_ts','market','pick','odds','ev','probability','placed_at','settled','won','profit','settled_at','source_match_id','home_score','away_score','score_status','score_updated_at']
    return [dict(zip(keys, tuple(r))) for r in rows]

def get_bet_by_id(bet_id):
    conn = _connect()
    c = conn.cursor()
    c.execute('SELECT * FROM bets WHERE id=?', (bet_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    keys = ['id','match','home','away','league','start_ts','market','pick','odds','ev','probability','placed_at','settled','won','profit','settled_at','source_match_id','home_score','away_score','score_status','score_updated_at']
    return dict(zip(keys, tuple(row)))

def delete_bets(bet_ids):
    if not bet_ids:
        return 0
    conn = _connect()
    c = conn.cursor()
    placeholders = ','.join('?' * len(bet_ids))
    c.execute(f'DELETE FROM bets WHERE id IN ({placeholders})', bet_ids)
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted

def delete_bets_by_date_range(start_date, end_date):
    import time
    from datetime import datetime, timezone, timedelta
    if not start_date and not end_date:
        return 0
    conn = _connect()
    c = conn.cursor()
    conditions = []
    params = []
    if start_date:
        start_ts = int(datetime.strptime(start_date, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp())
        conditions.append('start_ts >= ?')
        params.append(start_ts)
    if end_date:
        end_dt = datetime.strptime(end_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        end_ts = int((end_dt + timedelta(days=1)).timestamp()) - 1
        conditions.append('start_ts <= ?')
        params.append(end_ts)
    where = ' AND '.join(conditions)
    c.execute(f'DELETE FROM bets WHERE settled=0 AND {where}', params)
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted
