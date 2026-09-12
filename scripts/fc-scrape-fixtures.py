#!/usr/bin/env python3
"""Scrape 24h football fixtures from 1xbit into matches_detailed.json.

Schedule-only: NO model logic, NO picks, NO odds analysis. Each entry is a
bare fixture (info + empty picks) with coverage_status "market_only", so the
Schedule page can show kickoffs honestly while analysis stays engine-owned
(brief section 11.4.1: one-way data flow).

Existing entries are MERGED by match_id: any picks/qualified_picks already
locked by the engine are preserved, only info is refreshed.

Usage:
    python3 scripts/fc-scrape-fixtures.py [--window-hours 24] [--max-pages 60]
        [--out betting-machine-fc/matches_detailed.json]
"""
import argparse
import json
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'betting-machine-fc'))
import scraper_1xbit as sc  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--window-hours', type=float, default=24.0)
    ap.add_argument('--max-pages', type=int, default=60)
    ap.add_argument('--out', default=os.path.join(BASE_DIR, 'betting-machine-fc', 'matches_detailed.json'))
    args = ap.parse_args()

    try:
        rows = sc.list_matches_paginated(window_hours=args.window_hours, max_pages=args.max_pages)
    except Exception as exc:
        print(f'scrape failed: {exc}', file=sys.stderr)
        return 1

    now = time.time()
    fresh = {}
    for v in rows:
        try:
            mid = str(v.get('I'))
            start = float(v.get('S') or 0)
        except (TypeError, ValueError):
            continue
        if not mid or start <= now:
            continue
        fresh[mid] = {
            'info': {
                'match_id': mid,
                'home': v.get('O1'),
                'away': v.get('O2'),
                'league': v.get('L'),
                'start_ts': start,
                'coverage_status': 'market_only',
                'source': '1xbit',
                'scraped_at': now,
            },
            'picks': [],
            'qualified_picks': [],
        }

    merged = dict(fresh)
    if os.path.exists(args.out):
        try:
            with open(args.out, 'r', encoding='utf-8') as f:
                existing = json.load(f)
            for m in existing if isinstance(existing, list) else []:
                info = (m or {}).get('info') or {}
                mid = str(info.get('match_id') or '')
                if not mid:
                    continue
                try:
                    start = float(info.get('start_ts') or 0)
                except (TypeError, ValueError):
                    continue
                if start <= now:
                    continue  # drop expired
                if mid in merged:
                    # Preserve engine analysis; refresh info only.
                    merged[mid]['picks'] = m.get('picks') or []
                    merged[mid]['qualified_picks'] = m.get('qualified_picks') or []
                    for k in ('coverage_status', 'source'):
                        if info.get(k):
                            merged[mid]['info'][k] = info[k]
                else:
                    merged[mid] = m
        except Exception as exc:
            print(f'warning: could not merge existing file: {exc}', file=sys.stderr)

    ordered = sorted(merged.values(), key=lambda m: float((m.get('info') or {}).get('start_ts') or 0))
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(ordered, f, ensure_ascii=False, indent=2)
    print(f'fixtures: scraped={len(fresh)} total={len(ordered)} -> {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
