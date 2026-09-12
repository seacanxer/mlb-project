"""Local SQLite paper ledger: immutable locks and transactional result revisions.

This is an offline backend, not a choice of production deployment storage.
"""
import hashlib
import json
import sqlite3
from contextlib import contextmanager

from .contracts import identifier, require, timestamp, validate_snapshot
from .markets import PayoutProbabilities, settle_score
from .snapshot_store import canonical_bytes
from .value import expected_value


class PaperLedger:
    def __init__(self, path):
        self.path = str(path)
        with self._transaction() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS paper_locks (
                    bet_id TEXT PRIMARY KEY, fixture_id TEXT NOT NULL UNIQUE,
                    snapshot TEXT NOT NULL, locked_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS paper_revisions (
                    bet_id TEXT NOT NULL REFERENCES paper_locks(bet_id),
                    revision INTEGER NOT NULL, event_id TEXT NOT NULL,
                    payload TEXT NOT NULL, outcome TEXT NOT NULL, profit REAL NOT NULL,
                    PRIMARY KEY (bet_id, revision), UNIQUE (bet_id, event_id));
            ''')

    @contextmanager
    def _transaction(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            yield db
            if db.in_transaction:
                db.commit()
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    def lock(self, snapshot, *, locked_at):
        validate_snapshot(snapshot)
        timestamp(locked_at)
        require(snapshot['decision']['status'] == 'paper_candidate', 'Only selected paper candidates may lock')
        require(snapshot['prediction']['validation_status'] == 'approved', 'Paper lock requires segment approval evidence')
        calculated = expected_value(PayoutProbabilities(**snapshot['prediction']['payout']),
                                    snapshot['quote']['decimal_odds'])
        require(abs(calculated - snapshot['prediction']['ev_net']) <= 1e-10, 'Quote/EV mismatch')
        require(snapshot['capabilities']['official_enabled'] is False, 'Official ledger disabled')
        require(locked_at == snapshot['decision_at'] < snapshot['fixture']['kickoff_utc'],
                'Lock must use the evaluated decision time')
        payload = canonical_bytes(snapshot).decode()
        bet_id = 'paper-' + hashlib.sha256(payload.encode()).hexdigest()[:24]
        fixture = snapshot['fixture']['fixture_id']
        with self._transaction() as db:
            prior = db.execute('SELECT bet_id,snapshot FROM paper_locks WHERE fixture_id=?', (fixture,)).fetchone()
            if prior:
                require(prior[1] == payload, 'Fixture already locked with different evidence')
                return {'bet_id': prior[0], 'status': 'deduplicated'}
            db.execute('INSERT INTO paper_locks VALUES (?,?,?,?)', (bet_id, fixture, payload, locked_at))
        return {'bet_id': bet_id, 'status': 'created'}

    def settle(self, bet_id, event, *, expected_revision):
        """CAS prevents old results or racing corrections from replacing new state.

        A correction supplies a new event_id, expected current revision and newer
        observed_at. Void requires an explicit operator/source reason.
        """
        require(set(event) == {'event_id', 'fixture_id', 'source', 'observed_at',
                              'status', 'home_goals', 'away_goals', 'reason'}, 'Invalid result fields')
        for key in ('event_id', 'fixture_id', 'source'):
            identifier(event[key])
        timestamp(event['observed_at'])
        require(type(expected_revision) is int and expected_revision >= 0, 'Invalid expected revision')
        require(event['status'] in ('final', 'void'), 'Result is not settleable')
        require(type(event['reason']) is str, 'Invalid result reason')
        payload = canonical_bytes(event).decode()
        with self._transaction() as db:
            lock = db.execute('SELECT snapshot,locked_at FROM paper_locks WHERE bet_id=?', (bet_id,)).fetchone()
            require(lock is not None, 'Unknown bet')
            snapshot = json.loads(lock[0])
            require(event['fixture_id'] == snapshot['fixture']['fixture_id'], 'Result fixture mismatch')
            require(event['observed_at'] >= snapshot['fixture']['kickoff_utc'], 'Result predates kickoff')
            duplicate = db.execute('SELECT payload,revision FROM paper_revisions WHERE bet_id=? AND event_id=?',
                                   (bet_id, event['event_id'])).fetchone()
            if duplicate:
                require(duplicate[0] == payload, 'Result event ID conflict')
                return {'status': 'deduplicated', 'revision': duplicate[1]}
            latest = db.execute('SELECT revision,payload FROM paper_revisions WHERE bet_id=? ORDER BY revision DESC LIMIT 1',
                                (bet_id,)).fetchone()
            current = latest[0] if latest else 0
            require(current == expected_revision, 'Settlement revision conflict')
            if latest:
                require(event['observed_at'] > json.loads(latest[1])['observed_at'], 'Stale result correction')
            if event['status'] == 'void':
                require(bool(event['reason'].strip()) and event['home_goals'] is None
                        and event['away_goals'] is None, 'Void requires reason and no score')
                outcome, profit = 'void', 0.0
            else:
                require(all(type(event[k]) is int and event[k] >= 0 for k in ('home_goals', 'away_goals')),
                        'Final result requires integer scores')
                c = snapshot['contract']
                payout = settle_score(c['market'], c['side'], c['line_quarters'],
                                      event['home_goals'], event['away_goals'])
                outcome = next(k for k, v in vars(payout).items() if v == 1)
                profit = expected_value(payout, snapshot['quote']['decimal_odds'])
            revision = current + 1
            db.execute('INSERT INTO paper_revisions VALUES (?,?,?,?,?,?)',
                       (bet_id, revision, event['event_id'], payload, outcome, profit))
        return {'status': 'settled', 'revision': revision, 'outcome': outcome, 'profit_units': profit}

    def tracker(self):
        with self._transaction() as db:
            rows = db.execute('''SELECT l.bet_id,l.snapshot,r.revision,r.outcome,r.profit
                FROM paper_locks l LEFT JOIN paper_revisions r ON r.bet_id=l.bet_id
                AND r.revision=(SELECT MAX(revision) FROM paper_revisions WHERE bet_id=l.bet_id)
                ORDER BY l.locked_at,l.bet_id''').fetchall()
            revision_count = db.execute('SELECT COUNT(*) FROM paper_revisions').fetchone()[0]
        settled = [row for row in rows if row[2] is not None]
        profit = sum(row[4] for row in settled)
        by_version = {}
        for row in rows:
            snapshot = json.loads(row[1])
            key = '|'.join((snapshot['prediction']['formula_version'],
                            snapshot['prediction']['calibration_version'], snapshot['decision']['policy_version']))
            cohort = by_version.setdefault(key, {'settled': 0, 'pending': 0, 'profit_units': 0.0})
            cohort['settled' if row[2] else 'pending'] += 1
            cohort['profit_units'] += row[4] if row[2] else 0
        for cohort in by_version.values():
            cohort['roi'] = cohort['profit_units'] / cohort['settled'] if cohort['settled'] else None
        return {'schema_version': 'fc-paper-tracker-v1', 'cohort': 'paper_v2',
                'official_enabled': False, 'total': len(rows), 'pending': len(rows) - len(settled),
                'settled': len(settled), 'settled_stake_units': len(settled), 'profit_units': profit,
                'roi': profit / len(settled) if settled else None,
                'denominator': 'one unit per settled bet including push and void; pending excluded',
                'outcomes': {key: sum(row[3] == key for row in settled) for key in
                             ('full_win', 'half_win', 'push', 'half_loss', 'full_loss', 'void')},
                'revision_count': revision_count, 'by_version': by_version,
                'legacy_status': 'not_imported', 'roi_status': 'AVAILABLE' if settled else 'NO_SETTLED_PAPER_BETS'}
