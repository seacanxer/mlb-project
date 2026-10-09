#!/usr/bin/env python3
"""Append every CARD-SHOWN pick to an append-only local ledger.

Reads betting-machine-fc/matches_detailed.json (written by fc-scan-live.py)
and appends ONE row per fixture x displayed pick to
betting-machine-fc/projection_ledger.jsonl — exactly what PredictionBoard
renders: one pick per primary market from `projections`, one pick per
secondary market from `analysis.secondary_markets.markets` (first entry per
key, mirroring the card's `.find`). The full alternate-lines catalog
(`market_options`: every book line, both sides) is never card-shown and is
never logged.

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
import math
import os
import sys
import time
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FC_DIR = os.path.join(BASE_DIR, 'betting-machine-fc')
MATCHES_PATH = os.path.join(FC_DIR, 'matches_detailed.json')
LEDGER_PATH = os.path.join(FC_DIR, 'projection_ledger.jsonl')
CONFIG_PATH = os.path.join(FC_DIR, 'config.json')

# What the PredictionBoard card actually renders (components/fc/PredictionBoard.tsx):
#   primary cells:   projections.find(p => p.market === key) — ONE pick per market
#   secondary cells: secondary_markets.markets.find(row => row.market === key) — ditto
# The full alternate-lines catalog (market_options: every book line, both sides)
# is NEVER shown on the card, so it must never enter the ledger. Logging it
# exploded the ledger 10x and forced every aggregate hit rate to a structural
# 0.5/0.33 (both complementary sides always graded together).
PRIMARY_CARD_MARKETS = ('1x2', 'ah', 'ou', 'btts')
SECONDARY_CARD_MARKETS = ('corners_ou', 'corner_hdp', 'corner_1x2', 'cards_1x2', 'cards_hdp', 'cards_ou',
                          'team_cards_ou', 'red_card')


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
        base = {
            'match_id': match_id,
            'match': info.get('match') or f"{info.get('home')} vs {info.get('away')}",
            'home': info.get('home'), 'away': info.get('away'),
            'league': info.get('league'),
            'league_model': analysis.get('league_model'),
            'start_ts': start_ts,
        }
        seen_keys = set()

        def record(proj, source):
            if not isinstance(proj, dict):
                return
            market = (proj.get('market') or '').lower()
            if not market:
                return
            if market == '1x2':
                try:
                    odds = float(proj.get('odds'))
                    if not math.isfinite(odds) or odds < 1.30:
                        return
                except (TypeError, ValueError):
                    return
            side = proj.get('side')
            line_quarters = proj.get('line_quarters')
            if line_quarters is None and proj.get('line') is not None:
                # Secondary analysis rows carry `line`, not `line_quarters`.
                try:
                    line_quarters = int(round(float(proj.get('line')) * 4))
                except (TypeError, ValueError):
                    line_quarters = None
            team = proj.get('team')
            pick = proj.get('pick') or ''
            key = ledger_key(match_id, market, side, line_quarters, team, pick)
            if key in seen_keys:
                return
            seen_keys.add(key)
            try:
                probability = float(proj.get('probability'))
            except (TypeError, ValueError):
                return
            if not math.isfinite(probability) or not 0 <= probability <= 1:
                return
            rows.append({
                **base,
                'league_model': proj.get('league_model') or base['league_model'],
                'ledger_id': key,
                'first_seen_at': first_seen_at,
                'market': market, 'pick': pick, 'side': side,
                'team': team, 'line_quarters': line_quarters,
                'line': (None if line_quarters is None
                         else line_quarters / 4),
                'probability': round(probability, 4),
                'raw_probability': proj.get('raw_probability'),
                'probability_adjustment': proj.get('probability_adjustment'),
                'raw_price_probability': proj.get('raw_price_probability'),
                'market_probability': proj.get('market_probability'),
                'probability_model_weight': proj.get('probability_model_weight'),
                'payout': proj.get('payout'),
                'odds': proj.get('odds'),
                'ev': proj.get('ev'),
                'formula_version': (proj.get('formula_version')
                                    or proj.get('base_formula_version') or proj.get('model_version')),
                'base_formula_version': proj.get('base_formula_version'),
                'policy_version': proj.get('policy_version'),
                'coverage_status': proj.get('coverage_status'),
                'analysis_status': proj.get('analysis_status'),
                'gate_reasons': proj.get('gate_reasons'),
                'source': source,
                'quote_captured_at': proj.get('quote_captured_at'),
            })

        # Primary card cells: first projections item per market (mirrors .find).
        # qualified/picks collapse onto the same keys via dedup and are skipped
        # as separate sources; market_options (full alternate lines) is NEVER
        # card-shown and is never logged.
        shown_primary = set()
        for proj in match.get('projections') or []:
            market = ((proj or {}).get('market') or '').lower()
            if market in PRIMARY_CARD_MARKETS and market not in shown_primary:
                shown_primary.add(market)
                record(proj, 'card')
        # Secondary card cells: first secondary_markets.markets entry per key.
        secondary = (analysis.get('secondary_markets') or {}).get('markets') or []
        shown_secondary = set()
        for proj in secondary:
            market = ((proj or {}).get('market') or '').lower()
            if market in SECONDARY_CARD_MARKETS and market not in shown_secondary:
                shown_secondary.add(market)
                record({**proj, 'league_model': proj.get('league_model') or base['league_model'],
                        'quote_captured_at': proj.get('quote_captured_at') if proj.get('odds') is not None else None}, 'card-secondary')
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
