from datetime import date, datetime, timezone
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))

from football_formula_engine.secondary_markets import (
    CONFIG, _payout, _best_total, _best_corner_handicap, effective_sample, load_stat_rows, project_fixture,
)


def make_rows(n=80):
    rows = []
    start = date(2026, 1, 1)
    clubs = ['Spain', 'Croatia', 'Rival A', 'Rival B', 'Rival C', 'Rival D']
    for i in range(n):
        home = clubs[i % len(clubs)]
        away = clubs[(i + 1 + (i // len(clubs))) % len(clubs)]
        if home == away:
            away = clubs[(i + 2) % len(clubs)]
        rows.append({
            'date': date.fromordinal(start.toordinal() + i), 'home': home, 'away': away,
            'home_goals': 2, 'away_goals': 1,
            'home_corners': 7 + i % 3, 'away_corners': 3 + i % 2,
            'home_yellow': 2 + i % 2, 'away_yellow': 2 + (i + 1) % 2,
            'home_red': 1 if i % 20 == 0 else 0, 'away_red': 0,
            'home_fouls': 10, 'away_fouls': 12, 'referee': 'Ref A' if i % 4 else None,
        })
    # Provide adequate home and away samples for the target fixture.
    for i in range(18):
        rows.append({**rows[i], 'date': date.fromordinal(start.toordinal() + n + i),
                     'home': 'Spain', 'away': clubs[2 + i % 4]})
        rows.append({**rows[i], 'date': date.fromordinal(start.toordinal() + n + 18 + i),
                     'home': clubs[2 + i % 4], 'away': 'Croatia'})
    return rows


def test_empty_and_insufficient_statistics_are_state_c():
    kickoff = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())
    assert project_fixture([], 'Spain', 'Croatia', kickoff)['availability'] == 'C'
    sparse = make_rows(8)[:8]
    assert project_fixture(sparse, 'Spain', 'Croatia', kickoff)['availability'] == 'C'


def test_real_statistics_produce_state_b_without_fabricated_odds():
    rows = make_rows()
    kickoff = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())
    result = project_fixture(rows, 'Spain', 'Croatia', kickoff,
                             goal_projection={'home': 2.0, 'away': .8})
    assert result['availability'] == 'B'
    assert result['corners']['n_eff'] >= CONFIG['minimum_effective_league'] * 0 + 3
    assert result['cards']['n_eff'] >= 3
    assert result['market_odds_available'] is False
    assert all(row['odds'] is None and row['edge'] is None for row in result['markets'])
    assert {row['market'] for row in result['markets']} >= {
        'corners_ou', 'corner_hdp', 'cards_ou', 'team_cards_ou'}
    assert all(sum(row['payout'].values()) == pytest.approx(1) for row in result['markets']
               if row.get('payout'))


def test_asian_quarter_split_cards_settlement_probabilities():
    # At 2 goals on Over 2.25: half loss and half push, represented by Asian split.
    assert _payout([0, 0, 1], 2.25, 'over') == {
        'full_win': 0.0, 'half_win': 0.0, 'push': 0.0,
        'half_loss': 1.0, 'full_loss': 0.0}


def test_projection_lines_include_quarters_and_over_probability_is_monotone():
    import numpy as np
    distribution = np.asarray([.1, .2, .3, .25, .15])
    low = _best_total(distribution, 2.5, 'corners_ou')
    assert low['line'] in (2.25, 2.5, 2.75)
    assert sum(_payout(distribution, low['line'], 'over').values()) == pytest.approx(1)
    assert _payout(distribution, 2.25, 'over')['full_win'] >= _payout(distribution, 2.75, 'over')['full_win']


def test_corner_handicap_distribution_uses_home_minus_away_sign():
    import numpy as np
    symmetric = np.asarray([.05, .15, .3, .3, .15, .05])
    pick = _best_corner_handicap(symmetric, symmetric, 'Home', 'Away', 0.0)
    assert pick['side'] in ('home', 'away')
    assert pick['probability'] == pytest.approx(.385, abs=.02)  # ties push on level handicap
    opposite = _payout(np.convolve(symmetric, symmetric[::-1]), -5, 'home')
    assert opposite['full_win'] == pytest.approx(.385)


def test_effective_sample_downweights_old_observations():
    assert effective_sample([1, 1, 1]) == pytest.approx(3)
    assert effective_sample([1, .5, .25]) < 3


def test_csv_loader_keeps_missing_values_null(tmp_path):
    source = tmp_path / 'stats.csv'
    source.write_text('Date,HomeTeam,AwayTeam,FTHG,FTAG,HC,AC,HY,AY\n'
                      '01/08/26,Home,Away,1,0,8,,2,3\n', encoding='utf-8')
    rows = load_stat_rows([source])
    assert len(rows) == 1
    assert rows[0]['home_corners'] == 8
    assert rows[0]['away_corners'] is None


def test_score_only_lane_does_not_hide_later_corner_card_statistics(tmp_path):
    scores = tmp_path / 'scores.csv'
    stats = tmp_path / 'stats.csv'
    scores.write_text('Date,HomeTeam,AwayTeam,FTHG,FTAG\n01/08/26,Home,Away,1,0\n')
    stats.write_text('Date,HomeTeam,AwayTeam,FTHG,FTAG,HC,AC,HY,AY\n01/08/26,Home,Away,1,0,8,3,2,3\n')
    rows = load_stat_rows([scores, stats])
    assert len(rows) == 1
    assert rows[0]['home_corners'] == 8
    assert rows[0]['away_yellow'] == 3


def test_secondary_analysis_does_not_require_goal_model_or_market_quote():
    import runpy
    scanner = runpy.run_path(str(ROOT / 'scripts' / 'fc-scan-live.py'))
    kickoff = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())
    info = {'league': 'England. Premier League', 'home': 'Spain', 'away': 'Croatia',
            'start_ts': kickoff, 'match_id': 'fixture-1'}
    result = scanner['secondary_analysis'](info, {'E0': make_rows()})
    assert result['availability'] == 'B'
    offer = result['markets'][0]
    payload = scanner['secondary_pick_payload'](info, offer, None, None, kickoff-3600,
                                               'E0', 'secondary-test', 'unknown')
    assert payload['odds'] is None and payload['ev'] is None
    assert payload['quote_observation_id'] is None
    assert payload['line_quarters'] == round(offer['line'] * 4)
