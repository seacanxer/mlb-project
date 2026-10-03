#!/usr/bin/env python3
"""Append every scan projection to an append-only local ledger.

Reads betting-machine-fc/matches_detailed.json (written by fc-scan-live.py)
and appends one row per fixture x projection to
betting-machine-fc/projection_ledger.jsonl — projections, market_options and
qualified/single picks alike, primary AND secondary markets.

Dedup key (match_id, market, side, line_quarters, team, pick): first-seen
wins, so a fixture predicted across many scans is recorded once with its
earliest probability and model version. Later scans never overwrite history.

The ledger is LOCAL-ONLY (gitignored, like odds_quotes.jsonl). It feeds
scripts/fc-grade-projections.py, which produces the committed model
performance report in reports/ — fully separate from the ROI tracker
(bets.db -> tracker_snapshot.json), which only covers locked picks.

Usage:
  python scripts/fc-log-projections.py [--matches PATH] [--ledger PATH]
"""
import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FC_DIR = os.path.join(BASE_DIR, 'betting-machine-fc')
MATCHES_PATH = os.path.join(FC_DIR, 'matches_detailed.json')
LEDGER_PATH = os.path.join(FC_DIR, 'projection_ledger.jsonl')
CONFIG_PATH = os.path.join(FC_DIR, 'config.json')

SOURCE_ORDER = (('projections', 'projection'), ('market_options', 'market_option'),
                ('qualified_picks', 'qualified'), ('picks', 'pick'))


def ledger_key(match_id, market, side, line_quarters, team, pick):
    raw = '|'.join(str(value) for value in
                   (match_id, (market or '').lower(), (side or '').lower(),
                    line_quarters, (team or '').lower(), (pick or '').strip().lower()))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]


def load_keys(path):
    keys = set()
    if not os.path.exists(path):
        return keys
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                keys.add(json.loads(line)['ledger_id'])
            except (ValueError, KeyError, TypeError):
                continue
    return keys


def scan_time(config_path=CONFIG_PATH):
    try:
        with open(config_path, encoding='utf-8') as handle:
            stamp = json.load(handle).get('last_successful_scan_at')
        if stamp:
            return stamp
    except (OSError, ValueError):
        pass
    return datetime.now(timezone.utc).isoformat()


def collect_rows(matches, first_seen_at):
    rows = []
    for match in matches:
        info = match.get('info') or {}
        analysis = match.get('analysis') or {}
        match_id = str(info.get('match_id') or '')
        if not match_id:
            continue
        try:
            start_ts = int(float(info.get('start_ts') or 0))
        except (TypeError, ValueError):
            continue
        if start_ts <= 0:
            continue
        seen_in_scan = set()
        for field, source in SOURCE_ORDER:
            for proj in match.get(field) or []:
                if not isinstance(proj, dict):
                    continue
                market = (proj.get('market') or '').lower()
                if not market:
                    continue
                side = proj.get('side')
                line_quarters = proj.get('line_quarters')
                team = proj.get('team')
                pick = proj.get('pick') or ''
                key = ledger_key(match_id, market, side, line_quarters, team, pick)
                if key in seen_in_scan:
                    continue
                seen_in_scan.add(key)
                try:
                    probability = float(proj.get('probability'))
                except (TypeError, ValueError):
                    continue
                import math
                if not math.isfinite(probability) or not 0 <= probability <= 1:
                    continue
                rows.append({
                    'ledger_id': key,
                    'first_seen_at': first_seen_at,
                    'match_id': match_id,
                    'match': info.get('match') or f"{info.get('home')} vs {info.get('away')}",
                    'home': info.get('home'), 'away': info.get('away'),
                    'league': info.get('league'),
                    'league_model': (proj.get('league_model')
                                     or analysis.get('league_model')),
                    'start_ts': start_ts,
                    'market': market, 'pick': pick, 'side': side,
                    'team': team, 'line_quarters': line_quarters,
                    'line': (None if line_quarters is None
                             else line_quarters / 4),
                    'probability': round(probability, 4),
                    'odds': proj.get('odds'),
                    'ev': proj.get('ev'),
                    'formula_version': (proj.get('formula_version')
                                        or proj.get('base_formula_version')),
                    'base_formula_version': proj.get('base_formula_version'),
                    'policy_version': proj.get('policy_version'),
                    'coverage_status': proj.get('coverage_status'),
                    'analysis_status': proj.get('analysis_status'),
                    'gate_reasons': proj.get('gate_reasons'),
                    'source': source,
                    'quote_captured_at': proj.get('quote_captured_at'),
                })
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matches', default=MATCHES_PATH)
    parser.add_argument('--ledger', default=LEDGER_PATH)
    args = parser.parse_args(argv)
    try:
        with open(args.matches, encoding='utf-8') as handle:
            matches = json.load(handle)
    except (OSError, ValueError) as exc:
        print(json.dumps({'status': 'error', 'message': f'matches unreadable: {exc}'}))
        return 1
    known = load_keys(args.ledger)
    rows = collect_rows(matches, scan_time())
    fresh = [row for row in rows if row['ledger_id'] not in known]
    if fresh:
        with open(args.ledger, 'a', encoding='utf-8') as handle:
            for row in fresh:
                handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
    print(json.dumps({'status': 'ok', 'scanned': len(rows),
                      'appended': len(fresh), 'ledger': args.ledger}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
