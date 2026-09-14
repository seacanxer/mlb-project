"""Observed pre-match quotes. Source update time is never inferred from capture time."""
import json
import math
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .contracts import require
from .evaluation import canonical_bytes, seal


def quote_rows(markets):
    """Normalize 1xbit full-time contracts; AH lines retain side perspective."""
    for key, side in ((1, 'home'), (2, 'draw'), (3, 'away')):
        odds = (markets.get('odds_1x2') or {}).get(key)
        if odds is not None:
            yield '1x2', side, None, odds
    for side, odds in (markets.get('odds_btts') or {}).items():
        if side in ('yes', 'no'):
            yield 'btts', side, None, odds
    for line, sides in (markets.get('odds_ou') or {}).items():
        for key, side in (('9', 'over'), ('10', 'under')):
            odds = sides.get(key, sides.get(int(key)))
            if odds is not None:
                yield 'ou', side, float(line), odds
    for side in ('home', 'away'):
        for line, odds in (markets.get('odds_ah') or {}).get(side, []):
            yield 'ah', side, float(line), odds


class QuoteJournal:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS observations (
                    id TEXT PRIMARY KEY, fixture_id TEXT NOT NULL,
                    captured_at REAL NOT NULL, kickoff REAL NOT NULL,
                    provider TEXT NOT NULL, bookmaker TEXT NOT NULL,
                    payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS observations_lookup
                    ON observations(fixture_id, captured_at);
                CREATE TRIGGER IF NOT EXISTS observations_no_update
                    BEFORE UPDATE ON observations BEGIN SELECT RAISE(ABORT, 'immutable'); END;
                CREATE TRIGGER IF NOT EXISTS observations_no_delete
                    BEFORE DELETE ON observations BEGIN SELECT RAISE(ABORT, 'immutable'); END;
                CREATE TABLE IF NOT EXISTS research_decisions (
                    fixture_id TEXT NOT NULL, policy_id TEXT NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(fixture_id, policy_id));
                CREATE TRIGGER IF NOT EXISTS research_no_update
                    BEFORE UPDATE ON research_decisions BEGIN SELECT RAISE(ABORT, 'immutable'); END;
                CREATE TRIGGER IF NOT EXISTS research_no_delete
                    BEFORE DELETE ON research_decisions BEGIN SELECT RAISE(ABORT, 'immutable'); END;
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def record(self, info, markets, raw, *, captured_at, provider='1xbit',
               bookmaker='1xbit', source_updated_at=None):
        kickoff = float(info['start_ts'])
        require(math.isfinite(captured_at) and math.isfinite(kickoff)
                and 0 < captured_at < kickoff, 'Quote is not pre-match')
        require(source_updated_at is None or
                (math.isfinite(source_updated_at) and 0 < source_updated_at <= captured_at),
                'Invalid source update time')
        quotes, rejected = [], 0
        for market, side, line, price in quote_rows(markets):
            try:
                price = float(price)
                require(math.isfinite(price) and price > 1, 'Invalid price')
                q = None if line is None else round(line * 4)
                require(line is None or (math.isfinite(line) and abs(line * 4 - q) < 1e-8),
                        'Invalid quarter line')
                require(market != 'ou' or q >= 0, 'Negative total line')
                quotes.append({'market': market, 'side': side, 'line_quarters': q,
                               'decimal_odds': price, 'period': 'full_time_90_minutes'})
            except (ValueError, TypeError, OverflowError):
                rejected += 1
        snapshot = seal('observation', {
            'schema_version': 'fc-live-quote-observation-v1',
            'fixture_id': str(info['match_id']), 'fixture': info,
            'provider': provider, 'bookmaker': bookmaker, 'captured_at': captured_at,
            'source_updated_at': source_updated_at,
            'freshness': 'source_time_unknown' if source_updated_at is None else 'source_time_available',
            'quotes': quotes, 'rejected_quotes': rejected, 'raw': raw,
            'official_eligible': False,
        })
        payload = canonical_bytes(snapshot).decode()
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO observations VALUES (?, ?, ?, ?, ?, ?, ?)',
                       (snapshot['artifact_id'], str(info['match_id']), captured_at, kickoff,
                        provider, bookmaker, payload))
        return snapshot

    def as_of(self, fixture_id, decision_at, *, max_age_seconds=300):
        require(max_age_seconds > 0, 'Invalid max age')
        with self.connect() as db:
            rows = db.execute('''SELECT payload FROM observations WHERE fixture_id=?
                AND captured_at<=? AND captured_at>=? AND kickoff>?
                ORDER BY captured_at DESC, id''',
                (str(fixture_id), decision_at, decision_at - max_age_seconds, decision_at)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def record_research_decision(self, observation_id, contract, *, decision_at, policy_id, model):
        """First qualifying decision per fixture/policy, for prospective research only."""
        with self.connect() as db:
            row = db.execute('SELECT payload FROM observations WHERE id=?', (observation_id,)).fetchone()
            require(row is not None, 'Unknown quote observation')
            obs = json.loads(row[0])
            require(obs['captured_at'] <= decision_at < float(obs['fixture']['start_ts'])
                    and decision_at - obs['captured_at'] <= 300, 'Expired entry quote')
            require(any(all(q.get(k) == contract.get(k) for k in
                        ('market', 'side', 'line_quarters', 'decimal_odds')) for q in obs['quotes']),
                    'Entry contract does not match captured quote')
            payload = seal('research-decision', {
                'schema_version': 'fc-research-decision-v1', 'fixture_id': obs['fixture_id'],
                'policy_id': policy_id, 'decision_at': decision_at, 'observation_id': observation_id,
                'contract': contract, 'model': model, 'stake_units': 1,
                'status': 'research_only', 'official_enabled': False})
            db.execute('INSERT OR IGNORE INTO research_decisions VALUES (?, ?, ?)',
                       (obs['fixture_id'], policy_id, canonical_bytes(payload).decode()))
            saved = db.execute('SELECT payload FROM research_decisions WHERE fixture_id=? AND policy_id=?',
                               (obs['fixture_id'], policy_id)).fetchone()
            return json.loads(saved[0])

    def closing(self, fixture_id, kickoff, *, max_age_seconds=300):
        """Last observed same-contract price per book; gaps stay missing."""
        with self.connect() as db:
            rows = db.execute('''SELECT payload FROM observations WHERE fixture_id=?
                AND kickoff=? AND captured_at<? AND captured_at>=?
                ORDER BY captured_at DESC, id''',
                (str(fixture_id), kickoff, kickoff, kickoff - max_age_seconds)).fetchall()
        closing = {}
        for row in rows:
            obs = json.loads(row[0])
            for quote in obs['quotes']:
                key = (obs['provider'], obs['bookmaker'], quote['market'],
                       quote['side'], quote['line_quarters'])
                closing.setdefault(key, {'observation_id': obs['artifact_id'],
                                        'captured_at': obs['captured_at'], **quote})
        return closing

    def compare_sources(self, fixture_id, decision_at, *, max_age_seconds=300, max_skew_seconds=60):
        """Compare only identical contracts at nearby observation times, never approve."""
        observations = self.as_of(fixture_id, decision_at, max_age_seconds=max_age_seconds)
        latest = {}
        for obs in observations:
            updated = obs['source_updated_at']
            if updated is not None and decision_at - updated > max_age_seconds:
                continue
            for quote in obs['quotes']:
                contract = (quote['market'], quote['side'], quote['line_quarters'])
                key = (obs['provider'], obs['bookmaker'], contract)
                latest.setdefault(key, (obs, quote))
        pairs = []
        items = list(latest.items())
        for index, ((provider, book, contract), (obs, quote)) in enumerate(items):
            for ((other_provider, other_book, other_contract), (other, other_quote)) in items[index + 1:]:
                if book == other_book or contract != other_contract:
                    continue
                if abs(obs['captured_at'] - other['captured_at']) > max_skew_seconds:
                    continue
                pairs.append({'market': contract[0], 'side': contract[1], 'line_quarters': contract[2],
                              'observation_ids': [obs['artifact_id'], other['artifact_id']],
                              'bookmakers': [book, other_book],
                              'decimal_odds': [quote['decimal_odds'], other_quote['decimal_odds']],
                              'source_freshness_verified': obs['source_updated_at'] is not None
                                  and other['source_updated_at'] is not None})
        return {'status': 'MATCHED' if pairs else 'NO_MATCHED_SECOND_BOOKMAKER',
                'pairs': pairs, 'official_eligible': False}
