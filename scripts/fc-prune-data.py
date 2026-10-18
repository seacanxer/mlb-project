"""Retention for the FC engine's growing local data files.

live_quotes.db is append-only by design (UPDATE/DELETE triggers abort), so
pruning never edits it in place. The script builds a fresh journal holding:
  * every observation whose fixture kicked off within the retention window
    (or has not kicked off yet), and
  * every observation referenced by a research decision, at any age,
plus all research decisions. It then swaps the file atomically and keeps the
old one as a timestamped backup unless --no-backup is given.

odds_quotes.jsonl (optional cross-check log) keeps lines captured within the
retention window.

Dry run by default; pass --apply to write.

    python scripts/fc-prune-data.py                 # report only
    python scripts/fc-prune-data.py --apply --days 21
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FC_DIR = ROOT / 'betting-machine-fc'
sys.path.insert(0, str(FC_DIR))

from football_formula_engine.live_quotes import QuoteJournal  # noqa: E402


def prune_journal(path, cutoff, apply, backup):
    path = Path(path)
    if not path.exists():
        return {'file': str(path), 'status': 'missing'}
    before = path.stat().st_size
    src = sqlite3.connect(str(path))
    try:
        total = src.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
        referenced = set()
        for (payload,) in src.execute('SELECT payload FROM research_decisions'):
            try:
                referenced.add(json.loads(payload).get('observation_id'))
            except ValueError:
                continue
        keep_ids = {row[0] for row in src.execute(
            'SELECT id FROM observations WHERE kickoff >= ?', (cutoff,))} | (referenced - {None})
        decisions = src.execute('SELECT COUNT(*) FROM research_decisions').fetchone()[0]
    finally:
        src.close()
    report = {'file': str(path), 'bytes_before': before, 'observations': total,
              'kept': len(keep_ids), 'dropped': total - len(keep_ids),
              'research_decisions': decisions, 'status': 'dry_run'}
    if not apply or total == len(keep_ids):
        if apply:
            report['status'] = 'nothing_to_prune'
        return report
    fresh = path.with_suffix('.pruning.db')
    if fresh.exists():
        fresh.unlink()
    QuoteJournal(fresh)  # creates schema and immutability triggers
    db = sqlite3.connect(str(fresh))
    try:
        db.execute('ATTACH DATABASE ? AS old', (str(path),))
        db.execute('CREATE TEMP TABLE keep(id TEXT PRIMARY KEY)')
        db.executemany('INSERT INTO keep VALUES (?)', [(i,) for i in keep_ids])
        db.execute('INSERT INTO observations SELECT o.* FROM old.observations o JOIN keep k ON k.id = o.id')
        db.execute('INSERT INTO research_decisions SELECT * FROM old.research_decisions')
        db.commit()
        db.execute('DETACH DATABASE old')
        db.execute('VACUUM')
    finally:
        db.close()
    if backup:
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        shutil.copy2(path, path.with_name(f'{path.stem}.{stamp}.bak{path.suffix}'))
    os.replace(fresh, path)
    report.update(status='pruned', bytes_after=path.stat().st_size)
    return report


def prune_jsonl(path, cutoff, apply):
    path = Path(path)
    if not path.exists():
        return {'file': str(path), 'status': 'missing'}
    kept, dropped = [], 0
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            try:
                captured = datetime.fromisoformat(json.loads(line)['captured_at']).timestamp()
            except (ValueError, KeyError, TypeError):
                captured = None
            if captured is None or captured >= cutoff:
                kept.append(line)
            else:
                dropped += 1
    report = {'file': str(path), 'bytes_before': path.stat().st_size, 'kept': len(kept),
              'dropped': dropped, 'status': 'dry_run'}
    if apply and dropped:
        tmp = path.with_suffix('.jsonl.tmp')
        with open(tmp, 'w', encoding='utf-8') as handle:
            handle.writelines(kept)
        os.replace(tmp, path)
        report.update(status='pruned', bytes_after=path.stat().st_size)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--days', type=int, default=21, help='retention window after kickoff (default 21)')
    parser.add_argument('--apply', action='store_true', help='write changes (default: dry run)')
    parser.add_argument('--no-backup', action='store_true')
    parser.add_argument('--db', default=os.environ.get('FC_QUOTES_DB', str(FC_DIR / 'live_quotes.db')))
    parser.add_argument('--quotes-log', default=str(FC_DIR / 'odds_quotes.jsonl'))
    args = parser.parse_args(argv)
    if args.days < 7:
        parser.error('--days below 7 would drop quotes still needed for grading')
    cutoff = time.time() - args.days * 86400
    result = {'cutoff_days': args.days, 'apply': args.apply,
              'journal': prune_journal(args.db, cutoff, args.apply, not args.no_backup),
              'quotes_log': prune_jsonl(args.quotes_log, cutoff, args.apply)}
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
