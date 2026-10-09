from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[2]


def test_audit_distinguishes_after_event_results_and_complete_quote_benchmarks():
    module = runpy.run_path(str(ROOT/'scripts/fc-ledger-quality-audit.py'))
    base = dict(home='Home',away='Away',match='Home vs Away',match_id='m1',
                start_ts=1791500000,market='btts',side='yes',source='card',
                probability=.6,odds=1.9,ev=.14,first_seen_at='2026-10-08T00:00:00Z',
                quote_captured_at=1791400000,formula_version='test')
    entries = [dict(base,ledger_id='before'),
               dict(base,ledger_id='opposite',source='market_option',side='no',probability=.4,odds=1.9),
               dict(base,ledger_id='after',match_id='m2',home='Other',match='Other vs Away',
                    first_seen_at='2026-10-09T00:00:00Z')]
    grades = [dict(ledger_id=e['ledger_id'],market='btts',outcome='win',
                   model_probability=.6,actual={'home_goals':1,'away_goals':1}) for e in entries if e['source']=='card']
    report, rows = module['audit'](entries,grades)
    assert report['grading_mismatches'] == []
    assert report['all_confirmed']['overall']['n']==2
    assert report['prospective_timestamps_only']['overall']['n']==1
    assert report['prospective_complete_quote_benchmark']['btts']['n']==1
    assert report['walk_forward_weight_experiment']['btts']['oos_n']==0
    assert len(rows)==2


def test_score_disagreement_is_not_silently_accepted():
    module = runpy.run_path(str(ROOT/'scripts/fc-ledger-quality-audit.py'))
    entry = dict(ledger_id='bad',match_id='m1',source='card',market='btts',side='yes',
                 match='H vs A',start_ts=1791500000,probability=.6,odds=1.9)
    grade = dict(ledger_id='bad',market='btts',outcome='win',actual={'home_goals':2,'away_goals':0})
    report,_ = module['audit']([entry],[grade])
    assert len(report['grading_mismatches'])==1
    assert report['all_confirmed']['overall']['n']==0
