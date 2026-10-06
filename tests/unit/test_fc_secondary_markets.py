from datetime import date, datetime, timezone
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))

from football_formula_engine.secondary_markets import (
    CONFIG, _payout, _best_total, _best_corner_handicap, effective_sample, load_stat_rows, project_fixture,
    price_offered_totals, price_offered_handicap,
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


def test_national_secondary_analysis_uses_scoped_history():
    import runpy
    scanner = runpy.run_path(str(ROOT / 'scripts' / 'fc-scan-live.py'))
    kickoff = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())
    info = {'league': 'UEFA Nations League', 'home': 'Spain', 'away': 'Croatia', 'start_ts': kickoff,
            'match_id': 'national-fixture'}
    result = scanner['secondary_analysis'](info, {'INT_MEN': make_rows()})
    assert result['availability'] == 'B'
    assert any(m['market'].startswith('corner') for m in result['markets'])
    assert all('INT_MEN_stat_history.csv' in path for path in scanner['secondary_stat_files']('INT_MEN'))
    renamed = [{**r, 'home': 'Switzerland' if r['home'] == 'Spain' else r['home'],
                'away': 'North Macedonia' if r['away'] == 'Croatia' else r['away']}
               for r in make_rows()]
    alias_result = scanner['secondary_analysis'](
        {**info, 'home': 'Switzerland', 'away': 'Republic of North Macedonia'}, {'INT_MEN': renamed})
    assert alias_result['availability'] == 'B'
    # team_cards_ou must carry its side or the leg can never be settled.
    team_offer = next(row for row in result['markets'] if row['market'] == 'team_cards_ou')
    assert team_offer['team'] in ('home', 'away')
    team_payload = scanner['secondary_pick_payload'](info, team_offer, None, None, kickoff-3600,
                                                     'E0', 'secondary-test', 'unknown')
    assert team_payload['team'] == team_offer['team']
    assert scanner['secondary_pick_payload'](
        info, {**team_offer, 'team': None}, None, None,
        kickoff-3600, 'E0', 'secondary-test', 'unknown')['team'] is None


def test_1xbit_contract_always_carries_empty_secondary_books():
    sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
    import scraper_1xbit as sc
    base = sc.extract_markets({'I': 1, 'O1': 'H', 'O2': 'A', 'S': 0,
                               'L': 'X', 'WP': {}, 'E': [{'T': 1, 'C': 2.0, 'G': 1}]})
    assert base['odds_1x2'] == {1: 2.0}
    for key in ('odds_corners_ou', 'odds_corner_ah', 'odds_yellow_ou', 'odds_cards_ou'):
        assert base[key] == {}
    # Grouped (GE-style) corner entries parse with the same G/T codes as goals.
    ou, ah = sc._parse_ou_ah([
        [{'T': 9, 'P': 9.5, 'C': 1.9, 'G': 17}],
        [{'T': 10, 'P': 9.5, 'C': 1.9, 'G': 17}],
        [{'T': 3827, 'P': 9.25, 'C': 1.7, 'G': 99}],
        [{'T': 3828, 'P': 9.25, 'C': 2.1, 'G': 99}],
        [{'T': 7, 'P': -1.5, 'C': 1.9, 'G': 2}],
        [{'T': 8, 'P': 1.5, 'C': 1.9, 'G': 2}],
    ])
    assert ou[9.5] == {9: 1.9, 10: 1.9}
    assert ou[9.25] == {9: 1.7, 10: 2.1}
    assert (-1.5, 1.9) in ah['home'] and (1.5, 1.9) in ah['away']


def test_secondary_settlement_reuses_asian_math_with_push_as_void():
    import runpy
    settle = runpy.run_path(str(ROOT / 'scripts' / 'fc-settle-live.py'))
    fn = settle['settle_secondary_bet']
    # Corners OU: 6+5=11 over 9.5 wins; 5+4=9 over 9.5 loses; 9 on 9.0 pushes (void).
    assert fn('corners_ou', 'over', 38, 1.9, home_corners=6, away_corners=5) == (1, 0.9)
    assert fn('corners_ou', 'over', 38, 1.9, home_corners=5, away_corners=4) == (0, -1.0)
    assert fn('corners_ou', 'over', 36, 1.9, home_corners=5, away_corners=4) == (None, 0.0)
    assert fn('corners_ou', 'under', 38, 1.9, home_corners=5, away_corners=4)[0] == 1
    # Quarter line splits stake: 11 on over 10.75 = half win (+0.5u at 2.0).
    won, profit = fn('corners_ou', 'over', 43, 2.0, home_corners=6, away_corners=5)
    assert won == 1 and profit == pytest.approx(0.5)
    # Corner handicap reuses AH sign: HC-AC=2 covers home -1.5, pushes -2.
    assert fn('corner_hdp', 'home', -6, 1.9, home_corners=6, away_corners=4)[0] == 1
    assert fn('corner_hdp', 'home', -8, 1.9, home_corners=6, away_corners=4) == (None, 0.0)
    # Cards use booking points: 2+1 yellows + 1 red = 2+1+2=5 over 4.5 wins.
    assert fn('cards_ou', 'over', 18, 2.0, home_points=3, away_points=2) == (1, 1.0)
    assert fn('team_cards_ou', 'over', 6, 2.0, home_points=1, away_points=9, team='home')[0] == 0
    assert fn('team_cards_ou', 'over', 6, 2.0, home_points=1, away_points=9, team='away')[0] == 1
    # Red card is binary with no push.
    assert fn('red_card', 'yes', None, 3.0, red_total=1) == (1, 2.0)
    assert fn('red_card', 'no', None, 1.5, red_total=1)[0] == 0
    # Missing actuals never fabricate a loss.
    assert fn('corners_ou', 'over', 38, 1.9) is None
    assert fn('red_card', 'yes', None, 3.0) is None
    assert fn('nope', 'over', 38, 1.9, home_corners=1, away_corners=1) is None


def test_backtest_push_is_void_not_loss():
    import runpy
    backtest = runpy.run_path(str(ROOT / 'scripts' / 'fc-secondary-backtest.py'))
    outcome = backtest['_outcome']
    row = {'home_corners': 5, 'away_corners': 4, 'home_yellow': 2, 'away_yellow': 2,
           'home_red': 0, 'away_red': 0}
    assert outcome(row, 'corners_ou', {'side': 'over', 'line': 9}) is None
    assert outcome(row, 'corners_ou', {'side': 'over', 'line': 8.5}) == 1
    assert outcome(row, 'corner_hdp', {'side': 'home', 'line': -1}) is None
    assert outcome(row, 'corner_hdp', {'side': 'home', 'line': -0.5}) == 1


def test_offered_totals_price_every_book_line_without_shopping():
    import numpy as np
    distribution = np.asarray([.05, .1, .2, .3, .2, .1, .05])
    offers = price_offered_totals(distribution, 'corners_ou',
                                 {9.5: {9: 1.9, 10: 1.9}, 'bad': {}, 12.5: {9: 9.0, 10: 1.05},
                                  99.0: {9: 9.0, 10: 1.05}})
    by_line = {(o['line'], o['side']): o for o in offers}
    assert set(by_line) == {(9.5, 'over'), (9.5, 'under'), (12.5, 'over'), (12.5, 'under')}
    for offer in offers:
        assert offer['line_source'] == 'book'
        expected = _payout(distribution, offer['line'], offer['side'])
        assert offer['probability'] == pytest.approx(expected['full_win'] + expected['half_win'])
    assert by_line[(9.5, 'over')]['book_over'] == 1.9
    assert by_line[(9.5, 'under')]['book_under'] == 1.9
    assert by_line[(12.5, 'over')]['book_over'] == 9.0
    assert price_offered_totals(distribution, 'corners_ou', {}) == []
    assert price_offered_totals(distribution, 'corners_ou', None) == []


def test_offered_handicap_is_symmetric_and_skips_bad_legs():
    import numpy as np
    symmetric = np.asarray([.05, .15, .3, .3, .15, .05])
    offers = price_offered_handicap(symmetric, symmetric, 'Home', 'Away',
                                    {'home': [(-1.5, 1.9), ('bad', 1.9), (-5.5, 2.2)],
                                     'away': [(1.5, 1.9), (1.5, 0.5)]})
    by_key = {(o['side'], o['line']): o for o in offers}
    assert set(by_key) == {('home', -1.5), ('home', -5.5), ('away', 1.5)}
    # Mirror symmetry on symmetric distributions: home -1.5 == away -1.5.
    mirror = price_offered_handicap(symmetric, symmetric, 'Home', 'Away',
                                    {'away': [(-1.5, 1.9)]})
    assert mirror[0]['probability'] == pytest.approx(by_key[('home', -1.5)]['probability'])
    # Same handicap opposite sides are the no-vig pair: probabilities sum to ~1.
    assert by_key[('home', -1.5)]['probability'] + by_key[('away', 1.5)]['probability'] \
        == pytest.approx(1.0)
    assert by_key[('home', -1.5)]['pick'] == 'Home -1.5'
    assert by_key[('away', 1.5)]['pick'] == 'Away +1.5'
    assert all(o['line_source'] == 'book' for o in offers)
    assert all(sum(o['payout'].values()) == pytest.approx(1) for o in offers)


def test_project_fixture_with_book_replaces_shopped_corners():
    kickoff = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())
    rows = make_rows()
    plain = project_fixture(rows, 'Spain', 'Croatia', kickoff,
                            goal_projection={'home': 2.0, 'away': .8})
    assert {row['market'] for row in plain['markets']} >= {'corners_ou', 'corner_hdp'}
    assert all(row.get('line_source') == 'model-central' for row in plain['markets'])
    book = {'corners_ou': {9.5: {9: 1.9, 10: 1.9}, 10.5: {9: 2.1, 10: 1.7}},
            'corner_hdp': {'home': [(-1.5, 1.9)], 'away': [(1.5, 1.9)]}}
    priced = project_fixture(rows, 'Spain', 'Croatia', kickoff,
                             goal_projection={'home': 2.0, 'away': .8}, book=book)
    corner_lines = sorted({(row['market'], row['line'], row['side']) for row in priced['markets']
                           if row.get('line_source') == 'book'})
    assert ('corners_ou', 9.5, 'over') in corner_lines
    assert ('corners_ou', 10.5, 'under') in corner_lines
    assert ('corner_hdp', -1.5, 'home') in corner_lines
    assert ('corner_hdp', 1.5, 'away') in corner_lines
    assert not [row for row in priced['markets']
                if row['market'] in ('corners_ou', 'corner_hdp')
                and row.get('line_source') == 'model-central']
    # Cards book without explicit points opt-in stays shopped (units unverified).
    assert [row for row in priced['markets'] if row['market'] == 'cards_ou'
            and row.get('line_source') == 'model-central']
    opted = project_fixture(rows, 'Spain', 'Croatia', kickoff,
                            goal_projection={'home': 2.0, 'away': .8},
                            book={**book, 'cards_ou': {4.5: {9: 2.0, 10: 1.8}},
                                  'cards_units': 'points'})
    assert ('cards_ou', 4.5, 'over') in {(row['market'], row['line'], row['side'])
                                        for row in opted['markets']
                                        if row.get('line_source') == 'book'}


def test_papertrade_evaluate_applies_primary_gates_without_locking():
    import runpy
    paper = runpy.run_path(str(ROOT / 'scripts' / 'fc-secondary-papertrade.py'))
    scan = runpy.run_path(str(ROOT / 'scripts' / 'fc-scan-live.py'))
    certain = {'full_win': 0.6, 'half_win': 0.0, 'push': 0.0, 'half_loss': 0.0, 'full_loss': 0.4}
    verdict = paper['evaluate_offer'](certain, 2.0, 0.45, scan)
    assert verdict['pass'] is True
    assert verdict['ev'] == pytest.approx(0.6 * 1.0 - 0.4)
    assert verdict['market_probability'] == 0.45
    assert verdict['gate_reasons'] == []
    longshot = paper['evaluate_offer'](certain, 1.2, 0.8, scan)
    assert longshot['pass'] is False
    assert 'ODDS_OUTSIDE_VALUE_RANGE' in longshot['gate_reasons']
    assert paper['evaluate_offer'](certain, 'bad', 0.45, scan) is None
    assert paper['evaluate_offer'](certain, 2.0, None, scan)['pass'] is False


def test_secondary_quarter_ev_uses_half_and_push_payouts():
    import runpy
    scanner = runpy.run_path(str(ROOT / 'scripts' / 'fc-scan-live.py'))
    info = {'match_id':'q','home':'Home','away':'Away','league':'England. Premier League','start_ts':1900000000}
    offer = {'market':'corners_ou','side':'over','line':10.25,'pick':'Over 10.25',
             'probability':.5,'book_odds':2.0,'p_market_novig':.5,
             'payout':{'full_win':.4,'half_win':.1,'push':.1,'half_loss':.1,'full_loss':.3}}
    result = scanner['secondary_pick_payload'](info,offer,None,1800000000,1800000001,'E0','test','unknown')
    assert result['ev'] == pytest.approx(.1)
    assert result['conservative_ev'] == pytest.approx(.08)
    assert result['fair_odds'] == pytest.approx(1+.35/.45,abs=.001)
    assert not result['official_eligible']
