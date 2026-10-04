#!/usr/bin/env python3
"""Grade ledger projections against actual results. Separate from ROI.

Reads betting-machine-fc/projection_ledger.jsonl (written by
scripts/fc-log-projections.py) and, for rows past kickoff + 105 minutes,
resolves actuals and appends grades to
betting-machine-fc/projection_grades.jsonl:
  - goals markets (1x2/ah/ou/btts): FlashScore/FotMob/ESPN result feeds,
    settled with the same markets.settle_score math as the engine.
  - secondary markets (corners/cards): FotMob stat_history CSVs
    (HC/AC/HY/AY/HR/AR), booking-points convention yellow=1 + red=2.

Outcome granularity is win/half_win/push/half_loss/loss; Brier uses the
effective outcome (half = 0.5). No odds, no stake, no money — this measures
MODEL skill, never betting performance. The ROI tracker (bets.db ->
tracker_snapshot.json) is untouched and remains the only money report.

--report-out PATH writes reports/fc-model-performance.json plus a .md twin
(per-market hit rate, Brier, calibration gap). Pending/unknown rows are
reported as counts, never imputed.

Usage:
  python scripts/fc-grade-projections.py [--report-out reports/fc-model-performance.json]
"""
import argparse
import json
import os
import runpy
import sys
import time
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FC_DIR = os.path.join(BASE_DIR, 'betting-machine-fc')
sys.path.insert(0, FC_DIR)

from football_formula_engine.markets import settle_score  # noqa: E402

LEDGER_PATH = os.path.join(FC_DIR, 'projection_ledger.jsonl')
GRADES_PATH = os.path.join(FC_DIR, 'projection_grades.jsonl')
SETTLE_LIVE = os.path.join(BASE_DIR, 'scripts', 'fc-settle-live.py')
SCAN_PATH = os.path.join(BASE_DIR, 'scripts', 'fc-scan-live.py')
SETTLE_DELAY_S = 6300

GOAL_MARKETS = {'1x2', 'ah', 'ou', 'btts'}
SECONDARY_MARKETS = {'corners_ou', 'corner_hdp', 'cards_ou', 'team_cards_ou', 'red_card'}

# Card-only scope (mirrors components/fc/PredictionBoard.tsx): the report
# grades ONLY picks the card displays — one per market per fixture. The full
# alternate-lines catalog (ledger source 'market_option') is excluded: grading
# both complementary sides of every line forced hit rate to a structural
# 0.5/0.33 and drowned the model's actual chosen side.
# Legacy compatibility: before the card-only ledger, primary forecasts were
# logged as 'projection'/'qualified'/'pick' (same keys the card showed) and
# secondary single picks as 'projection' — all kept. Only 'market_option'
# (never card-shown) is dropped.
CARD_PRIMARY_SOURCES = {'projection', 'qualified', 'pick', 'card'}
CARD_SECONDARY_SOURCES = {'card-secondary', 'projection'}


def is_card_row(entry):
    market = (entry.get('market') or '').lower()
    source = entry.get('source')
    if market in GOAL_MARKETS:
        return source in CARD_PRIMARY_SOURCES
    if market in SECONDARY_MARKETS:
        return source in CARD_SECONDARY_SOURCES
    return False

_settle_ns = None
_scan_ns = None


def settle_ns():
    global _settle_ns
    if _settle_ns is None:
        _settle_ns = runpy.run_path(SETTLE_LIVE)
    return _settle_ns


def scan_ns():
    global _scan_ns
    if _scan_ns is None:
        _scan_ns = runpy.run_path(SCAN_PATH)
    return _scan_ns


def load_jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def payout_label(payout):
    if payout.push == 1.0:
        return 'push', 0.0
    score = payout.full_win + 0.5 * payout.half_win
    if payout.full_win == 1.0:
        return 'win', 1.0
    if payout.half_win == 1.0:
        return 'half_win', 0.5
    if payout.half_loss == 1.0:
        return 'half_loss', 0.5
    if payout.full_loss == 1.0:
        return 'loss', 0.0
    return ('win' if score >= 0.5 else 'loss'), score


def grade_goal(entry, lookups):
    sn = settle_ns()
    side = str(entry.get('side') or '').strip().lower()
    market, lq = entry['market'], entry.get('line_quarters')
    if market == '1x2' and side not in ('home', 'draw', 'away'):
        return None
    if market == 'btts':
        side = {'btts yes': 'yes', 'btts no': 'no'}.get(side, side)
        if side not in ('yes', 'no'):
            return None
    if market in ('ah', 'ou') and (lq is None or side not in
                                   (('home', 'away') if market == 'ah' else ('over', 'under'))):
        return None
    score = sn['result_for_bet'](entry.get('home'), entry.get('away'),
                                 entry['start_ts'], *lookups)
    if not score:
        return None
    home_goals, away_goals, source = score
    try:
        payout = settle_score(market, side, lq, home_goals, away_goals)
    except Exception:
        return None
    label, y_eff = payout_label(payout)
    return {'outcome': label, 'y_effective': y_eff,
            'actual': {'home_goals': home_goals, 'away_goals': away_goals,
                       'source': source}}


def stat_rows_for(code, cache):
    if code not in cache:
        sn = scan_ns()
        try:
            cache[code] = sn['load_secondary_rows'](sn['secondary_stat_files'](code))
        except Exception:
            cache[code] = []
    return cache[code]


def find_stat_row(rows, entry):
    sn = scan_ns()
    norm = sn['normalize_team_name']
    try:
        kickoff_date = datetime.fromtimestamp(float(entry['start_ts']),
                                              tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError):
        return None
    want_home, want_away = norm(entry.get('home') or ''), norm(entry.get('away') or '')
    for row in rows:
        try:
            day = row['date'].isoformat()
        except AttributeError:
            day = str(row.get('date'))
        if day != kickoff_date:
            continue
        if norm(row.get('home') or '') == want_home and norm(row.get('away') or '') == want_away:
            return row
    # Fuzzy fallback mirrors scan team matching (same 0.86 rule family).
    home_names = {r['home'] for r in rows if r.get('home')}
    away_names = {r['away'] for r in rows if r.get('away')}
    home = sn['match_team'](entry.get('home') or '', home_names)
    away = sn['match_team'](entry.get('away') or '', away_names)
    if not home or not away:
        return None
    for row in rows:
        try:
            day = row['date'].isoformat()
        except AttributeError:
            day = str(row.get('date'))
        if day == kickoff_date and row.get('home') == home and row.get('away') == away:
            return row
    return None


def grade_secondary(entry, cache):
    market = entry['market']
    side = str(entry.get('side') or '').strip().lower()
    lq, team = entry.get('line_quarters'), entry.get('team')
    rows = stat_rows_for(entry.get('league_model'), cache)
    if not rows:
        return None
    row = find_stat_row(rows, entry)
    if row is None:
        return None
    for key in ('home_corners', 'away_corners', 'home_yellow', 'away_yellow',
                'home_red', 'away_red'):
        if row.get(key) is None:
            return None
    actual = {'home_corners': int(row['home_corners']), 'away_corners': int(row['away_corners']),
              'home_points': int(row['home_yellow']) + 2 * int(row['home_red']),
              'away_points': int(row['away_yellow']) + 2 * int(row['away_red']),
              'red_total': int(row['home_red']) + int(row['away_red']),
              'source': 'fotmob_stat_history'}
    try:
        if market == 'corners_ou':
            if side not in ('over', 'under') or lq is None:
                return None
            payout = settle_score('ou', side, int(lq),
                                 actual['home_corners'], actual['away_corners'])
        elif market == 'corner_hdp':
            if side not in ('home', 'away') or lq is None:
                return None
            payout = settle_score('ah', side, int(lq),
                                 actual['home_corners'], actual['away_corners'])
        elif market == 'cards_ou':
            if side not in ('over', 'under') or lq is None:
                return None
            payout = settle_score('ou', side, int(lq),
                                 actual['home_points'], actual['away_points'])
        elif market == 'team_cards_ou':
            if side not in ('over', 'under') or lq is None or team not in ('home', 'away'):
                return None
            mine = actual['home_points'] if team == 'home' else actual['away_points']
            payout = settle_score('ou', side, int(lq), mine, 0)
        elif market == 'red_card':
            if side not in ('yes', 'no'):
                return None
            won = (side == 'yes') == (actual['red_total'] > 0)
            return {'outcome': 'win' if won else 'loss',
                    'y_effective': 1.0 if won else 0.0, 'actual': actual}
        else:
            return None
    except Exception:
        return None
    label, y_eff = payout_label(payout)
    return {'outcome': label, 'y_effective': y_eff, 'actual': actual}


def grade_pending(entries, graded_ids, now=None):
    now = now or time.time()
    sn = settle_ns()
    due = [e for e in entries
           if e.get('ledger_id') not in graded_ids
           and isinstance(e.get('start_ts'), (int, float))
           and e['start_ts'] <= now - SETTLE_DELAY_S]
    goal_due = [e for e in due if e.get('market') in GOAL_MARKETS]
    lookups = (None, None, None, None)
    if goal_due:
        target_dates = sorted({datetime.fromtimestamp(float(e['start_ts']), timezone.utc)
                               .date().isoformat() for e in goal_due})
        leagues = sorted({e.get('league') for e in goal_due if e.get('league')})
        feeds = sn['fetch_result_feeds'](target_dates, leagues, None, goal_due)
        lookups = (sn['scores_flashscore'].build_lookup(feeds.get('flashscore') or {}),
                   sn['scores_alt'].build_lookup(feeds.get('alt') or {}),
                   sn['scores_espn'].build_lookup(feeds.get('espn') or []),
                   sn['scores_fotmob'].build_lookup(feeds.get('fotmob') or {}))
    cache, grades = {}, []
    for entry in due:
        market = entry.get('market')
        if market in GOAL_MARKETS:
            result = grade_goal(entry, lookups)
        elif market in SECONDARY_MARKETS:
            result = grade_secondary(entry, cache)
        else:
            result = {'outcome': 'unsupported', 'y_effective': None, 'actual': None}
        if result is None:
            continue  # actuals not available yet; retry next run
        grades.append({'ledger_id': entry['ledger_id'], 'match_id': entry.get('match_id'),
                       'match': entry.get('match'), 'league': entry.get('league'),
                       'start_ts': entry.get('start_ts'),
                       'market': market, 'pick': entry.get('pick'),
                       'side': entry.get('side'), 'line': entry.get('line'),
                       'model_probability': entry.get('probability'),
                       'graded_at': datetime.now(timezone.utc).isoformat(), **result})
    return grades


def build_report(entries, grades, *, recent_n=100):
    by_id = {e['ledger_id']: e for e in entries if is_card_row(e)}
    card_ids = set(by_id)
    card_grades = [g for g in grades if g.get('ledger_id') in card_ids]
    graded_ids = {g['ledger_id'] for g in card_grades}
    by_market, overall = {}, {'n': 0, 'score': 0.0, 'brier': 0.0,
                              'mean_prob': 0.0, 'wins': 0, 'pushes': 0}
    for grade in card_grades:
        entry = by_id.get(grade['ledger_id'], {})
        market = grade.get('market') or entry.get('market') or 'unknown'
        bucket = by_market.setdefault(market, {'n': 0, 'score': 0.0, 'brier': 0.0,
                                               'mean_prob': 0.0, 'wins': 0,
                                               'losses': 0, 'pushes': 0,
                                               'half_wins': 0, 'half_losses': 0})
        bucket['n'] += 1
        prob = grade.get('model_probability')
        y_eff = grade.get('y_effective')
        if grade.get('outcome') == 'push':
            bucket['pushes'] += 1
            overall['pushes'] += 1
            continue
        if grade.get('outcome') == 'unsupported' or y_eff is None or prob is None:
            bucket['n'] -= 1
            continue
        bucket['score'] += y_eff
        bucket['brier'] += (prob - y_eff) ** 2
        bucket['mean_prob'] += prob
        overall['n'] += 1
        overall['score'] += y_eff
        overall['brier'] += (prob - y_eff) ** 2
        overall['mean_prob'] += prob
        if grade['outcome'] == 'win':
            bucket['wins'] += 1
            overall['wins'] += 1
        elif grade['outcome'] == 'loss':
            bucket['losses'] += 1
        elif grade['outcome'] == 'half_win':
            bucket['half_wins'] += 1
        elif grade['outcome'] == 'half_loss':
            bucket['half_losses'] += 1
    for bucket in list(by_market.values()) + [overall]:
        decisive = bucket['n'] - bucket.get('pushes', 0)
        bucket['decisive'] = decisive
        bucket['hit_rate'] = round(bucket['score'] / decisive, 4) if decisive else None
        bucket['mean_predicted'] = round(bucket['mean_prob'] / decisive, 4) if decisive else None
        bucket['brier'] = round(bucket['brier'] / decisive, 4) if decisive else None
        bucket['calibration_gap'] = (round(bucket['hit_rate'] - bucket['mean_predicted'], 4)
                                    if bucket['hit_rate'] is not None else None)
        del bucket['score']
        del bucket['mean_prob']
    pending = [e['ledger_id'] for e in by_id.values() if e.get('ledger_id') not in graded_ids]
    # Legacy grades (e.g. the first backfill) predate match/league/side/line
    # on the grade row itself — fall back to the ledger entry, which always
    # carries them. Without this the detail table renders blank matches.
    recent = []
    for grade in sorted(card_grades, key=lambda g: g.get('graded_at') or '', reverse=True)[:recent_n]:
        entry = by_id.get(grade.get('ledger_id'), {})
        row = {}
        for key in ('match', 'league', 'market', 'pick', 'side',
                    'outcome', 'graded_at'):
            row[key] = grade.get(key) if grade.get(key) is not None else entry.get(key)
        prob = grade.get('model_probability')
        if prob is None:
            prob = entry.get('probability')
        row['model_probability'] = prob
        line = grade.get('line')
        if line is None:
            line = entry.get('line')
        row['line'] = line
        recent.append(row)
    return {'generated_at': datetime.now(timezone.utc).isoformat(),
            'ledger_entries': len(by_id), 'graded': len(graded_ids),
            'pending': len(pending),
            'by_market': by_market, 'overall': overall,
            'recent': recent,
            'scope': 'card-only: one displayed pick per market per fixture '
                     '(alternate book lines never logged, never graded)',
            'note': ('Kinerja MODEL (probabilitas vs hasil). Bukan ROI: tanpa odds, '
                     'stake, atau lock. ROI tetap hanya dari tracker_snapshot.json. '
                     'Hanya pick yang tampil di card yang dinilai — satu sisi per '
                     'market — sehingga hit rate mencerminkan pilihan model.')}


def render_markdown(report):
    lines = ['# FC model performance report (projections ledger)',
             '',
             f'Digenerate: {report["generated_at"]} · Ledger: {report["ledger_entries"]} '
             f'entri · Ter-grade: {report["graded"]} · Pending: {report["pending"]}',
             '',
             '> Kinerja MODEL, bukan ROI. Tanpa odds/stake/lock. ROI tetap hanya dari tracker.',
             '',
             '> Hanya pick yang tampil di card (satu sisi per market) yang dinilai — '
             'alternate lines tidak dicatat dan tidak di-grade.',
             '',
             '| Market | N decisif | Hit rate | Mean pred | Brier | Cal gap | W / HW / HL / L / Push |',
             '|---|---:|---:|---:|---:|---:|---|']
    for market in sorted(report['by_market']):
        b = report['by_market'][market]
        fmt = lambda v: '—' if v is None else str(v)
        lines.append(f"| {market} | {b['decisive']} | {fmt(b['hit_rate'])} | "
                     f"{fmt(b['mean_predicted'])} | {fmt(b['brier'])} | {fmt(b['calibration_gap'])} | "
                     f"{b['wins']} / {b['half_wins']} / {b['half_losses']} / {b['losses']} / {b['pushes']} |")
    o = report['overall']
    lines.append(f"| **overall** | {o['decisive']} | {o['hit_rate']} | "
                 f"{o['mean_predicted']} | {o['brier']} | {o['calibration_gap']} | "
                 f"{o['wins']} / — / — / — / {o['pushes']} |")
    recent = report.get('recent') or []
    if recent:
        lines += ['', '## Detail pick terbaru (20 terakhir ter-grade)', '',
                  '| Match | Market | Pick | Prob | Hasil |',
                  '|---|---|---|---:|---|']
        for row in recent[:20]:
            lines.append(f"| {row.get('match')} | {row.get('market')} | {row.get('pick')} | "
                         f"{row.get('model_probability')} | {row.get('outcome')} |")
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger', default=LEDGER_PATH)
    parser.add_argument('--grades', default=GRADES_PATH)
    parser.add_argument('--report-out', default=None)
    parser.add_argument('--no-grade', action='store_true',
                        help='skip grading, only rebuild the report')
    args = parser.parse_args(argv)
    entries = load_jsonl(args.ledger)
    graded_ids = {g['ledger_id'] for g in load_jsonl(args.grades) if g.get('ledger_id')}
    fresh = []
    if not args.no_grade:
        fresh = grade_pending(entries, graded_ids)
        if fresh:
            with open(args.grades, 'a', encoding='utf-8') as handle:
                for grade in fresh:
                    handle.write(json.dumps(grade, ensure_ascii=False, allow_nan=False) + '\n')
    all_grades = load_jsonl(args.grades)
    summary = {'status': 'ok', 'ledger_entries': len(entries),
               'newly_graded': len(fresh), 'total_graded': len(all_grades)}
    if args.report_out:
        report = build_report(entries, all_grades)
        with open(args.report_out, 'w', encoding='utf-8') as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
        md_path = args.report_out[:-5] + '.md' if args.report_out.endswith('.json') else args.report_out + '.md'
        with open(md_path, 'w', encoding='utf-8') as handle:
            handle.write(render_markdown(report))
        summary['report'] = [args.report_out, md_path]
    print(json.dumps(summary))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
