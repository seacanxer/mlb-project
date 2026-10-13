from io import BytesIO
import json
from pathlib import Path
import runpy
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'betting-machine-fc'))
from football_formula_engine.catalog import select_markets
from football_formula_engine.live_quotes import QuoteJournal
from football_formula_engine.markets import PayoutProbabilities, asian_handicap
from football_formula_engine.reference_odds import capture, match_events
from football_formula_engine.score_matrix import build_score_matrix
from football_formula_engine.sharp_reference import (REFERENCE_EV_CAP, REFERENCE_EV_GATE,
    fair_probabilities, latest_reference_quotes)
from football_formula_engine.value import effective_win_loss

SCAN = runpy.run_path(str(ROOT/'scripts/fc-scan-live.py'))
KICKOFF = 2_000_000_000


def quotes(rows):
    return {(m, s, q): {'decimal_odds': o} for m, s, q, o in rows}


def test_fair_probabilities_require_complete_complementary_contracts():
    fair = fair_probabilities(quotes([
        ('1x2', 'home', None, 2.0), ('1x2', 'draw', None, 3.6), ('1x2', 'away', None, 4.0),
        ('ou', 'over', 10, 1.9), ('ou', 'under', 10, 1.9),
        ('ou', 'over', 11, 2.1),                       # no under at 2.75: not priced
        ('ah', 'home', -2, 1.8), ('ah', 'away', 2, 2.05),
        ('btts', 'yes', None, 1.7),                    # incomplete BTTS
    ]))
    assert sum(fair[('1x2', s, None)] for s in ('home', 'draw', 'away')) == pytest.approx(1)
    assert fair[('ou', 'over', 10)] == pytest.approx(.5)
    assert ('ou', 'over', 11) not in fair
    assert fair[('ah', 'home', -2)] + fair[('ah', 'away', 2)] == pytest.approx(1)
    assert fair[('ah', 'home', -2)] > .5
    assert not any(key[0] == 'btts' for key in fair)


def test_latest_reference_quotes_use_only_reference_book_newest_first():
    observations = [
        {'bookmaker': 'pinnacle', 'artifact_id': 'new', 'captured_at': 2,
         'quotes': [{'market': '1x2', 'side': 'home', 'line_quarters': None, 'decimal_odds': 2.1}]},
        {'bookmaker': '1xbit', 'artifact_id': 'x', 'captured_at': 2,
         'quotes': [{'market': '1x2', 'side': 'draw', 'line_quarters': None, 'decimal_odds': 3.0}]},
        {'bookmaker': 'Pinnacle', 'artifact_id': 'old', 'captured_at': 1,
         'quotes': [{'market': '1x2', 'side': 'home', 'line_quarters': None, 'decimal_odds': 1.9}]},
    ]
    latest = latest_reference_quotes(observations, 'pinnacle')
    assert latest == {('1x2', 'home', None): {'decimal_odds': 2.1, 'observation_id': 'new',
                                              'captured_at': 2, 'source_updated_at': None}}


def test_reference_mode_prices_ev_against_sharp_fair_probability():
    payout = PayoutProbabilities(full_win=.7, full_loss=.3)   # model view is ignored
    priced = SCAN['opp'](payout, 2.2, .45, market='1x2', reference=.48,
                         reference_mode=True, gated=False)
    assert priced['probability'] == pytest.approx(.48)
    assert priced['ev'] == pytest.approx(2.2 * .48 - 1)
    assert priced['gate_reasons'] == []
    assert priced['probability_model_weight'] == 0.0
    # Below the 2% gate and above the implausibility cap are withheld.
    assert SCAN['opp'](payout, 2.2, .45, market='1x2', reference=.46, reference_mode=True) is None
    high = (1 + REFERENCE_EV_CAP + .05) / 2.2
    assert SCAN['opp'](payout, 2.2, .45, market='1x2', reference=high, reference_mode=True) is None
    assert REFERENCE_EV_GATE == .02


def test_reference_mode_preserves_push_shape_on_quarter_lines():
    dist = build_score_matrix(1.6, 1.1, 0.0)
    payout = asian_handicap(dist, 'home', -1)              # home -0.25: half-loss on draw
    priced = SCAN['opp'](payout, 1.95, .5, market='ah', reference=.56,
                         reference_mode=True, gated=False)
    adjusted = PayoutProbabilities(**priced['payout'])
    win, loss = effective_win_loss(adjusted)
    assert win / (win + loss) == pytest.approx(.56)
    assert adjusted.push == pytest.approx(payout.push)
    assert adjusted.full_loss / adjusted.half_loss == pytest.approx(payout.full_loss / payout.half_loss)


def book():
    return {'odds_1x2': {1: 2.30, 2: 3.40, 3: 3.30},
            'odds_ou': {'2.5': {'9': 1.95, '10': 1.90}},
            'odds_ah': {'home': [(-0.5, 2.30)], 'away': [(0.5, 1.68)]}}


def test_missing_reference_never_produces_a_value_pick():
    dist = build_score_matrix(1.9, 0.8, 0.0)              # strong home view from the model
    rows = SCAN['price_fixture'](dist, book(), gated=False, reference_fair={})
    assert rows and all('REFERENCE_UNAVAILABLE' in o['gate_reasons'] for _, _, o in rows)
    assert select_markets(rows)[1] == []


def test_reference_value_is_selected_on_the_matching_contract_only():
    dist = build_score_matrix(1.2, 1.2, 0.0)
    fair = {('1x2', 'home', None): .46, ('1x2', 'draw', None): .28, ('1x2', 'away', None): .26}
    rows = SCAN['price_fixture'](dist, book(), gated=False, reference_fair=fair)
    by_label = {label: o for _, label, o in rows}
    assert by_label['Home']['ev'] == pytest.approx(2.30 * .46 - 1)
    assert by_label['Home']['gate_reasons'] == []
    assert 'REFERENCE_UNAVAILABLE' in by_label['Over 2.5']['gate_reasons']
    value = select_markets(rows)[1]
    assert [(m, label) for m, label, _ in value] == [('1x2', 'Home')]


def test_match_events_requires_both_teams_and_kickoff():
    resolve = {'Arsenal FC': 'Arsenal', 'Arsenal': 'Arsenal', 'Chelsea': 'Chelsea',
               'Chelsea FC': 'Chelsea', 'Spurs': 'Tottenham', 'Tottenham Hotspur': 'Tottenham'}.get
    fixtures = [{'match_id': 1, 'home': 'Arsenal FC', 'away': 'Chelsea FC', 'start_ts': KICKOFF},
                {'match_id': 2, 'home': 'Spurs', 'away': 'Arsenal FC', 'start_ts': KICKOFF}]
    iso = '2033-05-18T03:33:20Z'
    events = [{'id': 'a', 'home_team': 'Arsenal', 'away_team': 'Chelsea', 'commence_time': iso},
              {'id': 'b', 'home_team': 'Arsenal', 'away_team': 'Tottenham Hotspur', 'commence_time': iso},
              {'id': 'c', 'home_team': 'Tottenham Hotspur', 'away_team': 'Arsenal',
               'commence_time': '2033-05-18T05:33:20Z'}]
    pairs = match_events(events, fixtures, resolve)
    assert [(info['match_id'], event['id']) for info, event in pairs] == [(1, 'a')]


def test_capture_records_reference_quotes_readable_by_the_scanner(tmp_path):
    event = {'id': 'evt', 'sport_key': 'soccer_epl', 'home_team': 'Arsenal', 'away_team': 'Chelsea',
             'commence_time': '2033-05-18T03:33:20Z',
             'bookmakers': [{'key': 'pinnacle', 'markets': [
                 {'key': 'h2h', 'outcomes': [{'name': 'Arsenal', 'price': 2.10},
                                             {'name': 'Draw', 'price': 3.50},
                                             {'name': 'Chelsea', 'price': 3.70}]},
                 {'key': 'totals', 'outcomes': [{'name': 'Over', 'price': 1.95, 'point': 2.5},
                                                {'name': 'Under', 'price': 1.93, 'point': 2.5}]},
                 {'key': 'spreads', 'outcomes': [{'name': 'Arsenal', 'price': 2.02, 'point': -0.5},
                                                 {'name': 'Chelsea', 'price': 1.88, 'point': 0.5}]},
             ]}]}

    def opener(url, timeout):
        assert 'soccer_epl' in url and 'bookmakers=pinnacle' in url
        return BytesIO(json.dumps([event]).encode())

    journal = QuoteJournal(tmp_path/'quotes.db')
    fixture = {'match_id': '77', 'home': 'Arsenal FC', 'away': 'Chelsea FC', 'start_ts': KICKOFF}
    resolve = lambda name: name.replace(' FC', '')
    report = capture({'E0': [fixture]}, {'E0': resolve}, journal, api_key='k',
                     bookmaker='pinnacle', opener=opener, now=KICKOFF - 600)
    assert report['E0']['matched'] == 1 and report['E0']['recorded'] == 1
    fair = fair_probabilities(latest_reference_quotes(
        journal.as_of('77', KICKOFF - 300, max_age_seconds=900), 'pinnacle'))
    assert set(fair) == {('1x2', 'home', None), ('1x2', 'draw', None), ('1x2', 'away', None),
                         ('ou', 'over', 10), ('ou', 'under', 10),
                         ('ah', 'home', -2), ('ah', 'away', 2)}


def test_high_win_tier_and_low_odds_floor():
    from football_formula_engine.sharp_reference import value_tier
    payout = PayoutProbabilities(full_win=.6, full_loss=.4)
    fav = SCAN['opp'](payout, 1.40, .70, market='1x2', reference=.74, reference_mode=True)
    assert fav is not None and fav['value_tier'] == 'high_win'      # 1.40 now inside floor 1.30
    dog = SCAN['opp'](payout, 3.40, .28, market='1x2', reference=.31, reference_mode=True)
    assert dog['value_tier'] == 'value'
    assert value_tier(.55) == 'high_win' and value_tier(.549) == 'value'
    assert SCAN['opp'](payout, 1.25, .8, market='1x2', reference=.9, reference_mode=True) is None


def test_reference_movement_reports_open_and_current_fair():
    from football_formula_engine.sharp_reference import reference_movement

    def obs(at, home, draw, away, book='pinnacle'):
        return {'bookmaker': book, 'captured_at': at, 'quotes': [
            {'market': '1x2', 'side': s, 'line_quarters': None, 'decimal_odds': o}
            for s, o in (('home', home), ('draw', draw), ('away', away))]}
    moves = reference_movement([obs(3, 1.80, 3.8, 4.6), obs(1, 2.10, 3.4, 3.7),
                                obs(2, 1.50, 4.0, 7.0, book='1xbit')], 'pinnacle')
    opened, now = moves[('1x2', 'home', None)]
    assert now > opened                       # home steamed from 2.10 to 1.80
    assert reference_movement([], 'pinnacle') == {}
