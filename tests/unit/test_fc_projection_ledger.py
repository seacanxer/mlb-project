"""Ledger + grading report for ALL projections (model skill, not ROI)."""
import json
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = str(ROOT / 'scripts' / 'fc-log-projections.py')
GRADE_PATH = str(ROOT / 'scripts' / 'fc-grade-projections.py')


def make_matches():
    base = {'info': {'match_id': 'm1', 'match': 'H vs A', 'home': 'H', 'away': 'A',
                     'league': 'L', 'start_ts': 1790000000},
            'analysis': {'league_model': 'E0'}}
    projs = [
        {'market': 'ou', 'pick': 'Over 2.5', 'side': 'over', 'line_quarters': 10,
         'probability': 0.6, 'odds': 1.9, 'ev': 0.05, 'formula_version': 'v1',
         'coverage_status': 'full', 'analysis_status': 'value_candidate',
         'gate_reasons': [], 'quote_captured_at': 1789999900},
        {'market': 'corners_ou', 'pick': 'Over 9.5', 'side': 'over', 'line_quarters': 38,
         'probability': 0.55, 'odds': None, 'ev': None, 'formula_version': 'v2',
         'coverage_status': 'projection', 'analysis_status': 'projection',
         'gate_reasons': ['SECONDARY_MARKET_NO_ODDS'], 'quote_captured_at': None},
    ]
    return [{**base, 'projections': projs, 'market_options': list(projs),
             'qualified_picks': [projs[0]], 'picks': [projs[0]]}]


def test_log_appends_once_with_first_seen_dedup(tmp_path):
    log = runpy.run_path(LOG_PATH)
    matches = tmp_path / 'matches.json'
    ledger = tmp_path / 'ledger.jsonl'
    matches.write_text(json.dumps(make_matches()), encoding='utf-8')
    assert log['main'](['--matches', str(matches), '--ledger', str(ledger)]) == 0
    rows = [json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines()]
    # Card-only: the ou forecast (first per market in projections). The
    # corners_ou forecast is secondary (comes from analysis.markets, absent
    # here) and the duplicated market_options catalog is never logged.
    assert len(rows) == 1
    assert rows[0]['market'] == 'ou'
    assert rows[0]['source'] == 'card'
    assert rows[0]['line'] == 2.5
    first = {row['ledger_id']: row['first_seen_at'] for row in rows}
    # Second scan with changed probabilities appends nothing (first-seen wins).
    changed = make_matches()
    for field in ('projections', 'market_options', 'qualified_picks', 'picks'):
        for proj in changed[0][field]:
            proj['probability'] = 0.99
    matches.write_text(json.dumps(changed), encoding='utf-8')
    assert log['main'](['--matches', str(matches), '--ledger', str(ledger)]) == 0
    rows2 = [json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines()]
    assert len(rows2) == 1
    assert {row['ledger_id']: row['first_seen_at'] for row in rows2} == first
    assert all(row['probability'] != 0.99 for row in rows2)


def test_log_takes_secondary_display_pick_from_analysis_markets(tmp_path):
    log = runpy.run_path(LOG_PATH)
    matches = tmp_path / 'matches.json'
    ledger = tmp_path / 'ledger.jsonl'
    data = make_matches()
    data[0]['analysis']['secondary_markets'] = {
        'availability': 'B',
        'markets': [
            {'market': 'corners_ou', 'side': 'over', 'line': 9.5,
             'pick': 'Over 9.5', 'probability': 0.55, 'odds': None,
             'ev': None, 'formula_version': 'v2'},
            {'market': 'corners_ou', 'side': 'over', 'line': 10.5,
             'pick': 'Over 10.5', 'probability': 0.4, 'odds': None,
             'ev': None, 'formula_version': 'v2'},
        ],
    }
    matches.write_text(json.dumps(data), encoding='utf-8')
    assert log['main'](['--matches', str(matches), '--ledger', str(ledger)]) == 0
    rows = [json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines()]
    # Card shows first-per-key only: ou forecast + first corners line.
    assert {(row['market'], row.get('line')) for row in rows} == {('ou', 2.5), ('corners_ou', 9.5)}
    assert {row['source'] for row in rows} == {'card', 'card-secondary'}


def test_payout_label_and_report_math():
    grade = runpy.run_path(GRADE_PATH)
    from football_formula_engine.markets import settle_score
    label, y = grade['payout_label'](settle_score('ou', 'over', 10, 2, 1))
    assert (label, y) == ('win', 1.0)
    label, y = grade['payout_label'](settle_score('ou', 'over', 8, 1, 1))
    assert (label, y) == ('push', 0.0)
    label, y = grade['payout_label'](settle_score('ou', 'under', 9, 1, 1))
    assert (label, y) == ('half_win', 0.5)
    entries = [{'ledger_id': 'a', 'market': 'ou', 'probability': 0.6, 'source': 'projection'},
               {'ledger_id': 'b', 'market': 'ou', 'probability': 0.8, 'source': 'projection'},
               {'ledger_id': 'c', 'market': 'ou', 'probability': 0.5, 'source': 'projection'}]
    grades = [{'ledger_id': 'a', 'market': 'ou', 'outcome': 'win',
               'y_effective': 1.0, 'model_probability': 0.6},
              {'ledger_id': 'b', 'market': 'ou', 'outcome': 'loss',
               'y_effective': 0.0, 'model_probability': 0.8},
              {'ledger_id': 'c', 'market': 'ou', 'outcome': 'push',
               'y_effective': 0.0, 'model_probability': 0.5}]
    report = grade['build_report'](entries, grades)
    bucket = report['by_market']['ou']
    assert bucket['decisive'] == 2 and bucket['pushes'] == 1
    assert bucket['hit_rate'] == 0.5
    assert bucket['mean_predicted'] == 0.7
    assert bucket['brier'] == round(((0.6 - 1) ** 2 + (0.8 - 0) ** 2) / 2, 4)
    assert bucket['calibration_gap'] == round(0.5 - 0.7, 4)
    assert report['pending'] == 0
    assert 'Bukan ROI' in report['note']
    # Card-only scope must be disclosed, not hidden.
    assert 'satu sisi per' in report['note']


def test_report_embeds_newest_pick_detail_first():
    grade = runpy.run_path(GRADE_PATH)
    entries = [{'ledger_id': 'a', 'market': 'ou', 'probability': 0.6, 'source': 'card'},
               {'ledger_id': 'b', 'market': 'ou', 'probability': 0.4, 'source': 'card'}]
    grades = [
        {'ledger_id': 'a', 'match': 'H vs A', 'league': 'L', 'market': 'ou',
         'pick': 'Over 2.5', 'side': 'over', 'line': 2.5,
         'model_probability': 0.6, 'outcome': 'win', 'y_effective': 1.0,
         'graded_at': '2026-10-04T00:00:02+00:00'},
        {'ledger_id': 'b', 'match': 'X vs Y', 'league': 'L', 'market': 'ou',
         'pick': 'Under 2.5', 'side': 'under', 'line': 2.5,
         'model_probability': 0.4, 'outcome': 'loss', 'y_effective': 0.0,
         'graded_at': '2026-10-04T00:00:01+00:00'},
    ]
    report = grade['build_report'](entries, grades, recent_n=100)
    assert [row['pick'] for row in report['recent']] == ['Over 2.5', 'Under 2.5']
    assert report['recent'][0]['match'] == 'H vs A'
    assert set(report['recent'][0]) == {'match', 'league', 'market', 'pick', 'side',
                                        'line', 'model_probability', 'outcome', 'graded_at'}
    capped = grade['build_report'](entries, grades, recent_n=1)
    assert len(capped['recent']) == 1


def test_recent_falls_back_to_ledger_for_legacy_grades():
    grade = runpy.run_path(GRADE_PATH)
    entries = [{'ledger_id': 'old', 'match': 'H vs A', 'league': 'E0', 'market': 'ah',
                'pick': 'H -1.5', 'side': 'home', 'line': -1.5, 'probability': 0.6,
                'source': 'projection'}]
    grades = [{'ledger_id': 'old', 'market': 'ah', 'model_probability': 0.6,
               'outcome': 'win', 'y_effective': 1.0,
               'graded_at': '2026-10-04T00:00:01+00:00'}]
    report = grade['build_report'](entries, grades)
    assert report['recent'][0]['match'] == 'H vs A'
    assert report['recent'][0]['league'] == 'E0'
    assert report['recent'][0]['side'] == 'home'
    assert report['recent'][0]['line'] == -1.5


def test_report_excludes_never_shown_alternate_lines():
    grade = runpy.run_path(GRADE_PATH)
    entries = [
        {'ledger_id': 'card', 'match': 'H vs A', 'market': 'ou', 'pick': 'Over 2.5',
         'side': 'over', 'line': 2.5, 'probability': 0.6, 'source': 'card'},
        {'ledger_id': 'alt', 'match': 'H vs A', 'market': 'ou', 'pick': 'Over 3.5',
         'side': 'over', 'line': 3.5, 'probability': 0.4, 'source': 'market_option'},
    ]
    grades = [
        {'ledger_id': 'card', 'market': 'ou', 'model_probability': 0.6,
         'outcome': 'win', 'y_effective': 1.0, 'graded_at': '2026-10-04T00:00:02+00:00'},
        {'ledger_id': 'alt', 'market': 'ou', 'model_probability': 0.4,
         'outcome': 'loss', 'y_effective': 0.0, 'graded_at': '2026-10-04T00:00:01+00:00'},
    ]
    report = grade['build_report'](entries, grades)
    assert report['ledger_entries'] == 1
    assert report['graded'] == 1
    assert report['pending'] == 0
    assert report['by_market']['ou']['decisive'] == 1
    assert [row['pick'] for row in report['recent']] == ['Over 2.5']
