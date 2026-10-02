#!/usr/bin/env python3
"""Paper-trade secondary corner markets against live 1xbit books. READ-ONLY.

For up to --limit upcoming fixtures that have a fitted goal-model league and
secondary stat history:
  1. fetch the main listing row (no writes, no journal)
  2. fetch secondary sub-game books (corners OU/AH via TI=2; cards only with
     --cards-points, whose points-vs-count mapping is still unverified)
  3. project_fixture(..., book=...) — book-priced offers, line_source 'book',
     status stays 'projection'
  4. per offered line: model probability vs proportional no-vig, EV/CEV with
     the SAME gates as the primary scan (odds 1.6-2.5, EV>=0.01, CEV>=0).

NEVER locks, NEVER writes picks.json / bets.db / journal. Output is one JSON
report (--out) plus a stdout summary.

Known limitations (also stamped into the report):
  - goal_projection=None: no market-goal dominance blend for corners/cards.
  - corners only by default; cards need --cards-points (units unverified).
  - no calibration: calibrated_prob is null, probabilities are raw model outs.
  - ROI is null: paper prices, no settlement of these legs yet.
"""
import argparse
import json
import os
import runpy
import sys
import time
from types import SimpleNamespace

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FC_DIR = os.path.join(BASE_DIR, 'betting-machine-fc')
sys.path.insert(0, FC_DIR)

from football_formula_engine.secondary_markets import project_fixture  # noqa: E402
from football_formula_engine.value import (  # noqa: E402
    expected_value, fair_odds, proportional_no_vig)

SCAN_PATH = os.path.join(BASE_DIR, 'scripts', 'fc-scan-live.py')
NAMESPACE = None


def scanner():
    global NAMESPACE
    if NAMESPACE is None:
        NAMESPACE = runpy.run_path(SCAN_PATH)
    return NAMESPACE


def evaluate_offer(payout_dict, price, market_novig, scan):
    """Pure EV verdict for one offered side. Returns None when unpriceable."""
    try:
        price = float(price)
    except (TypeError, ValueError):
        return None
    if not price > 1:
        return None
    import math
    if not math.isfinite(price):
        return None
    payout = SimpleNamespace(**payout_dict)
    try:
        ev = expected_value(payout, price)
    except Exception:
        return None
    try:
        fo = fair_odds(payout)
    except Exception:
        fo = None
    cev = ev - scan['UNCERTAINTY_PENALTY']
    reasons = []
    if not (scan['ODDS_FLOOR'] <= price <= scan['ODDS_CAP']):
        reasons.append('ODDS_OUTSIDE_VALUE_RANGE')
    if ev < scan['EV_GATE']:
        reasons.append('EV_BELOW_VALUE_THRESHOLD')
    if cev < 0:
        reasons.append('CONSERVATIVE_EV_BELOW_THRESHOLD')
    if market_novig is None:
        reasons.append('NOVIG_UNAVAILABLE')
    return {'odds': price, 'fair_odds': fo, 'ev': ev, 'conservative_ev': cev,
            'market_probability': market_novig, 'gate_reasons': reasons,
            'pass': not reasons}


def novig_pair(over, under):
    try:
        return proportional_no_vig([float(over), float(under)])
    except Exception:
        return None


def papertrade(limit=5, window_hours=24.0, delay=0.4, cards_points=False, max_scan=60):
    scan = scanner()
    sc = scan['sc']
    matches = sc.list_matches_paginated(count=100, window_hours=window_hours, max_pages=10)
    cache, fixtures, offers = {}, [], []
    evaluated = 0
    for row in matches[:max_scan]:
        if evaluated >= limit:
            break
        code = scan['model_code'](row.get('L'))
        if code not in scan['LEAGUES']:
            continue
        info = {'match_id': str(row.get('I')), 'home': row.get('O1'),
                'away': row.get('O2'), 'league': row.get('L'),
                'start_ts': row.get('S')}
        if code not in cache:
            try:
                cache[code] = scan['load_secondary_rows'](
                    scan['secondary_stat_files'](code))
            except Exception as exc:
                fixtures.append({**info, 'league_model': code, 'skipped': f'STAT_LOAD_FAILED: {exc}'})
                continue
        rows = cache[code]
        teams = {r[side] for r in rows for side in ('home', 'away')}
        home = scan['match_team'](info['home'] or '', teams)
        away = scan['match_team'](info['away'] or '', teams)
        if not home or not away:
            fixtures.append({**info, 'league_model': code, 'skipped': 'SECONDARY_TEAM_UNMATCHED'})
            continue
        # Cheap plain projection first: no book fetch unless the model is state B.
        try:
            plain = project_fixture(rows, home, away, info['start_ts'])
        except Exception as exc:
            fixtures.append({**info, 'league_model': code, 'skipped': f'PROJECTION_FAILED: {exc}'})
            continue
        if plain['availability'] != 'B':
            fixtures.append({**info, 'league_model': code,
                             'skipped': plain.get('reason') or 'UNAVAILABLE'})
            continue
        try:
            secondary_books = sc.extract_secondary_markets(row['I'])
        except Exception as exc:
            fixtures.append({**info, 'league_model': code, 'skipped': f'SECONDARY_FETCH_FAILED: {exc}'})
            continue
        time.sleep(delay)
        book = {'corners_ou': secondary_books.get('odds_corners_ou') or {},
                'corner_hdp': secondary_books.get('odds_corner_ah') or {}}
        if cards_points:
            book['cards_ou'] = secondary_books.get('odds_cards_ou') or {}
            book['cards_units'] = 'points'
        if not book['corners_ou'] and not book['corner_hdp']:
            fixtures.append({**info, 'league_model': code, 'skipped': 'SECONDARY_BOOK_EMPTY'})
            continue
        try:
            projection = project_fixture(rows, home, away, info['start_ts'], book=book)
        except Exception as exc:
            fixtures.append({**info, 'league_model': code, 'skipped': f'PROJECTION_FAILED: {exc}'})
            continue
        fixture = {**info, 'league_model': code,
                   'book_lines': {k: len(v) for k, v in book.items() if isinstance(v, dict)},
                   'subgame_ids': secondary_books.get('secondary_subgame_ids') or {}}
        fixtures.append(fixture)
        evaluated += 1
        hdp_pairs = {}
        for offer in projection['markets']:
            if offer.get('line_source') != 'book' or offer['market'] != 'corner_hdp':
                continue
            hdp_pairs.setdefault(offer['line'], {})[offer['side']] = offer.get('book_odds')
        for offer in projection['markets']:
            if offer.get('line_source') != 'book':
                continue
            if offer['market'] == 'corners_ou':
                pair = novig_pair(offer.get('book_over'), offer.get('book_under'))
                price = offer.get('book_over') if offer['side'] == 'over' else offer.get('book_under')
                novig = pair[0] if pair and offer['side'] == 'over' else (pair[1] if pair else None)
            elif offer['market'] == 'corner_hdp':
                legs = hdp_pairs.get(offer['line'], {})
                pair = novig_pair(legs.get('home'), legs.get('away'))
                price = offer.get('book_odds')
                novig = pair[0] if pair and offer['side'] == 'home' else (pair[1] if pair else None)
            elif offer['market'] == 'cards_ou':
                pair = novig_pair(offer.get('book_over'), offer.get('book_under'))
                price = offer.get('book_over') if offer['side'] == 'over' else offer.get('book_under')
                novig = pair[0] if pair and offer['side'] == 'over' else (pair[1] if pair else None)
            else:
                continue
            verdict = evaluate_offer(offer['payout'], price, novig, scan)
            offers.append({
                'match': f"{info['home']} vs {info['away']}", 'league': info['league'],
                'market': offer['market'], 'pick': offer['pick'], 'side': offer['side'],
                'line': offer['line'], 'probability': round(offer['probability'], 4),
                'book_over': offer.get('book_over'), 'book_under': offer.get('book_under'),
                'book_odds': offer.get('book_odds'), 'evaluation': verdict,
            })
    passing = [o for o in offers if (o['evaluation'] or {}).get('pass')]
    by_market = {}
    for offer in offers:
        bucket = by_market.setdefault(offer['market'], {'offers': 0, 'pass': 0})
        bucket['offers'] += 1
        bucket['pass'] += (offer['evaluation'] or {}).get('pass', False)
    return {
        'mode': 'paper_trade_no_lock',
        'model_version': 'fc-secondary-counts-v1',
        'fixtures_scanned': len(fixtures),
        'fixtures': fixtures,
        'offers_evaluated': len(offers),
        'offers': offers,
        'passing_offers': len(passing),
        'by_market': by_market,
        'gates': {'odds_floor': scan['ODDS_FLOOR'], 'odds_cap': scan['ODDS_CAP'],
                  'ev_gate': scan['EV_GATE'],
                  'uncertainty_penalty': scan['UNCERTAINTY_PENALTY']},
        'limitations': [
            'goal_projection=None: no market-goal dominance blend applied',
            'corners only unless --cards-points (TI=10 points-vs-count mapping unverified)',
            'no calibration: probabilities are raw model outputs, calibrated_prob null',
            'paper prices at scan time: no closing-line value, no settlement of these legs',
        ],
        'roi_claim': 'unavailable_paper_trade_no_settlement',
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=5)
    parser.add_argument('--window-hours', type=float, default=24.0)
    parser.add_argument('--delay', type=float, default=0.4)
    parser.add_argument('--max-scan', type=int, default=60)
    parser.add_argument('--cards-points', action='store_true')
    parser.add_argument('--out', default=None)
    args = parser.parse_args(argv)
    report = papertrade(limit=max(1, args.limit), window_hours=args.window_hours,
                        delay=args.delay, cards_points=args.cards_points,
                        max_scan=max(1, args.max_scan))
    print(f"fixtures={report['fixtures_scanned']} offers={report['offers_evaluated']} "
          f"passing={report['passing_offers']}")
    for market, bucket in sorted(report['by_market'].items()):
        print(f"  {market}: {bucket['pass']}/{bucket['offers']} pass gate")
    for offer in report['offers']:
        ev = offer['evaluation']
        status = 'PASS' if ev and ev['pass'] else 'watch'
        detail = '' if not ev else f"p={offer['probability']} odds={ev['odds']} ev={ev['ev']:.3f}"
        print(f"  [{status}] {offer['match']} {offer['pick']} {detail}")
    rendered = json.dumps(report, indent=2, allow_nan=False, default=str)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as handle:
            handle.write(rendered)
        print(f'wrote {args.out}')
    else:
        print(rendered)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
