#!/usr/bin/env python3
"""Refresh the CC0 senior-international results snapshot without losing valid data."""
import csv
import hashlib
import io
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'betting-machine-fc/data/international_results.csv'
META = ROOT / 'betting-machine-fc/data/international_results.source.json'
RAW_URL = 'https://raw.githubusercontent.com/martj42/international_results/master/results.csv'
MAX_BYTES = 8_000_000


def inspect(payload):
    rows = list(csv.DictReader(io.StringIO(payload.decode('utf-8-sig'))))
    required = {'date', 'home_team', 'away_team', 'home_score', 'away_score', 'neutral'}
    if not rows or not required <= set(rows[0]):
        raise ValueError('Invalid international-results schema')
    latest = ''
    for row in rows:
        datetime.strptime(row['date'], '%Y-%m-%d')
        if not row['home_team'] or not row['away_team'] or row['neutral'] not in ('TRUE', 'FALSE'):
            raise ValueError('Invalid international result row')
        if min(int(row['home_score']), int(row['away_score'])) < 0:
            raise ValueError('Negative result score')
        latest = max(latest, row['date'])
    if latest > datetime.now(timezone.utc).date().isoformat():
        raise ValueError('Future result in source')
    return len(rows), latest


def main():
    request = urllib.request.Request(RAW_URL, headers={'User-Agent': 'FC-national-results-refresh/1.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError('Source exceeds size limit')
    count, latest = inspect(payload)
    old_count, old_latest = inspect(DATA.read_bytes()) if DATA.exists() else (0, '')
    if count < old_count or latest < old_latest:
        raise ValueError('Source moved backwards; preserving local snapshot')
    meta = json.loads(META.read_text(encoding='utf-8')) if META.exists() else {}
    meta.update(source='https://github.com/martj42/international_results/blob/master/results.csv',
                license='CC0-1.0', scope="men's senior international results only",
                retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
                sha256=hashlib.sha256(payload).hexdigest(),
                rows=count, latest_result_date=latest)
    DATA.with_suffix('.csv.tmp').write_bytes(payload)
    DATA.with_suffix('.csv.tmp').replace(DATA)
    META.with_suffix('.json.tmp').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    META.with_suffix('.json.tmp').replace(META)
    print(json.dumps({'status': 'updated', 'rows': count, 'latest_result_date': latest,
                      'sha256': meta['sha256']}))


if __name__ == '__main__':
    main()
