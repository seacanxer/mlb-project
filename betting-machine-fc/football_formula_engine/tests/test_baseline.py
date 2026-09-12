from dataclasses import replace
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
from football_formula_engine.baseline import estimate_ratio_lambdas, fit_ratio_baseline
from football_formula_engine.contracts import ContractError
from football_formula_engine.data import normalize_football_data_row


def match(home, away, hg, ag, row):
    value, _ = normalize_football_data_row(
        {'Date': f'{row:02d}/01/2025', 'Time': '12:00', 'HomeTeam': home, 'AwayTeam': away, 'FTHG': hg, 'FTAG': ag},
        competition_id='TEST', season='2425', source_file='test.csv', source_row=row + 1, timezone_name='UTC')
    return value


def test_ratio_baseline_is_explicit_benchmark():
    matches = [match('A', 'B', 2, 1, 1), match('B', 'A', 1, 1, 2),
               match('A', 'B', 1, 0, 3), match('B', 'A', 2, 1, 4)]
    model = fit_ratio_baseline(matches, cutoff_utc=max(m.result_available_at_utc for m in matches))
    a = matches[0].home_team_id; b = matches[0].away_team_id
    home, away = estimate_ratio_lambdas(a, b, model)
    assert home > 0 and away > 0
    assert model['model'] == 'ratio-baseline-not-approved'


def test_ratio_baseline_rejects_missing_coverage():
    matches = [match('A', 'B', 2, 1, 1)]
    model = fit_ratio_baseline(matches, cutoff_utc=matches[0].result_available_at_utc)
    with pytest.raises(ContractError): estimate_ratio_lambdas(matches[0].home_team_id, matches[0].away_team_id, model)


def test_ratio_baseline_enforces_cutoff():
    value = match('A', 'B', 2, 1, 1)
    with pytest.raises(ContractError): fit_ratio_baseline([value], cutoff_utc=value.result_available_at_utc - 1)
