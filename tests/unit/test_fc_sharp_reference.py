from io import BytesIO
import sqlite3
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
    report = capture({'soccer_epl': [fixture]}, journal, api_key='k',
                     bookmaker='pinnacle', opener=opener, now=KICKOFF - 600)
    assert report['soccer_epl']['matched'] == 1 and report['soccer_epl']['recorded'] == 1
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


# --- Coverage incident 13 Oct 2026: UCL, artifacts, pairing, output classes ---
from football_formula_engine.reference_odds import (is_market_artifact, pair_events,
    reference_sport_key)


def test_team_vs_player_rows_are_market_artifacts_not_fixtures():
    assert is_market_artifact('England. Premier League. Team vs Player')
    assert is_market_artifact('UEFA Champions League. Team vs Player')
    assert not is_market_artifact('UEFA Champions League')
    assert not is_market_artifact('England. Premier League')


def test_ucl_maps_to_reference_only_not_a_domestic_model():
    assert SCAN['model_code']('UEFA Champions League') is None
    assert reference_sport_key('UEFA Champions League') == 'soccer_uefa_champs_league'
    assert reference_sport_key('UEFA Europa League') == 'soccer_uefa_europa_league'
    assert reference_sport_key('England. Championship', 'E1') == 'soccer_efl_champ'
    assert reference_sport_key('Spain. Youth Championship') is None
    assert SCAN['model_code']('Turkey. SuperLiga') == 'T1'


UCL = [('RC Lens', 'Sporting', 'Lens', 'Sporting Lisbon'),
       ('Sabah Baku', 'Slavia Prague', 'Sabah FK', 'Slavia Praha'),
       ('Arsenal', 'Lille', 'Arsenal', 'Lille'),
       ('Atletico Madrid', 'Manchester United', 'Atlético Madrid', 'Manchester United'),
       ('Galatasaray', 'Barcelona', 'Galatasaray', 'Barcelona'),
       ('Inter', 'Club Brugge', 'Inter Milan', 'Club Brugge KV'),
       ('RB Leipzig', 'PSV', 'RasenBallsport Leipzig', 'PSV Eindhoven'),
       ('Viking', 'Bayern', 'Viking FK', 'Bayern Munich'),
       ('Villarreal', 'Napoli', 'Villarreal', 'SSC Napoli')]


def test_ucl_provider_variants_pair_uniquely_within_kickoff_slot():
    iso = '2033-05-18T03:33:20Z'
    fixtures = [{'match_id': str(i), 'home': h, 'away': a, 'start_ts': KICKOFF}
                for i, (h, a, _, _) in enumerate(UCL)]
    events = [{'id': f'e{i}', 'home_team': h, 'away_team': a, 'commence_time': iso}
              for i, (_, _, h, a) in enumerate(UCL)]
    pairs = pair_events(events, fixtures)
    assert sorted((info['match_id'], event['id']) for info, event in pairs) == \
        sorted((str(i), f'e{i}') for i in range(len(UCL)))


def test_pairing_rejects_swapped_sides_wrong_kickoff_and_ambiguity():
    iso = '2033-05-18T03:33:20Z'
    fixture = {'match_id': '1', 'home': 'Arsenal', 'away': 'Lille', 'start_ts': KICKOFF}
    swapped = [{'id': 's', 'home_team': 'Lille', 'away_team': 'Arsenal', 'commence_time': iso}]
    late = [{'id': 'l', 'home_team': 'Arsenal', 'away_team': 'Lille',
             'commence_time': '2033-05-18T03:35:30Z'}]
    assert pair_events(swapped, [fixture]) == []
    assert pair_events(late, [fixture]) == []
    twins = [{'id': 'm1', 'home_team': 'Manchester United', 'away_team': 'Lille', 'commence_time': iso},
             {'id': 'm2', 'home_team': 'Manchester City', 'away_team': 'Lille', 'commence_time': iso}]
    assert pair_events(twins, [{'match_id': '2', 'home': 'Manchester', 'away': 'Lille',
                                'start_ts': KICKOFF}]) == []


def test_reference_quotes_build_a_market_implied_distribution():
    from football_formula_engine.market_goals import infer_market_goals
    from football_formula_engine.sharp_reference import quotes_to_markets
    q = quotes([('1x2', 'home', None, 1.80), ('1x2', 'draw', None, 3.80), ('1x2', 'away', None, 4.60),
                ('ou', 'over', 11, 2.05), ('ou', 'under', 11, 1.85)])
    goals = infer_market_goals(quotes_to_markets(q))
    assert goals is not None and goals['home'] > goals['away']
    assert 2.3 < goals['total'] < 3.3


# --- Card projections: confidence tier instead of elimination ---
from football_formula_engine.confidence import confidence_tier, display_markets, tier_hit_rate


def test_confidence_tiers_and_hit_rates():
    assert confidence_tier(.74) == 'TINGGI' and confidence_tier(.65) == 'TINGGI'
    assert confidence_tier(.6) == 'SEDANG' and confidence_tier(.5) == 'RENDAH'
    assert confidence_tier(.3) == 'SPEKULATIF' and confidence_tier(None) == 'SPEKULATIF'
    assert tier_hit_rate('TINGGI') > tier_hit_rate('SEDANG') > tier_hit_rate('RENDAH')


def test_display_shows_every_market_even_without_value():
    dist = build_score_matrix(1.6, 0.9, 0.0)
    mk = dict(book(), odds_btts={'yes': 1.95, 'no': 1.85})
    mk['odds_ou']['3.5'] = {'9': 3.1, '10': 1.36}       # extreme alt line must not be shown
    rows = SCAN['price_fixture'](dist, mk, gated=False, reference_fair={})
    shown = display_markets(rows)
    assert [m for m, _, _ in shown] == ['1x2', 'ah', 'ou', 'btts']
    assert all('REFERENCE_UNAVAILABLE' in o['gate_reasons'] for _, _, o in shown)   # display, not value
    ou = [o for m, _, o in shown if m == 'ou'][0]
    assert ou['line_quarters'] == 10                     # balanced main line
    one = [(label, o) for m, label, o in shown if m == '1x2'][0]
    assert one[0] == 'Home' and one[1]['confidence_source'] == 'market'


def test_display_uses_sharp_confidence_when_matched():
    dist = build_score_matrix(1.2, 1.2, 0.0)
    fair = {('1x2', 'home', None): .30, ('1x2', 'draw', None): .28, ('1x2', 'away', None): .42}
    rows = SCAN['price_fixture'](dist, book(), gated=False, reference_fair=fair)
    one = [(label, o) for m, label, o in display_markets(rows) if m == '1x2'][0]
    assert one[0] == 'Away' and one[1]['confidence'] == pytest.approx(.42)
    assert one[1]['confidence_source'] == 'sharp'


def test_unmodelled_leagues_get_a_lane():
    from football_formula_engine.reference_odds import reference_sport_key
    assert reference_sport_key('Copa Sudamericana') == 'soccer_conmebol_copa_sudamericana'
    assert reference_sport_key('Algeria. Ligue 2') is None      # -> market-only lane in the scanner


def test_display_prefers_value_candidate_in_its_market():
    dist = build_score_matrix(1.2, 1.2, 0.0)
    fair = {('1x2', 'home', None): .46, ('1x2', 'draw', None): .28, ('1x2', 'away', None): .26}
    shown = display_markets(SCAN['price_fixture'](dist, book(), gated=False, reference_fair=fair))
    one = [(label, o) for m, label, o in shown if m == '1x2'][0]
    assert one[0] == 'Home' and one[1]['gate_reasons'] == []


def test_model_lane_confidence_uses_model_when_no_sharp_price():
    from football_formula_engine.confidence import source_label
    dist = build_score_matrix(2.0, 0.7, 0.0)             # model strongly favours home
    rows = SCAN['price_fixture'](dist, book(), gated=False, reference_fair={}, model_confidence=True)
    one = [(label, o) for m, label, o in display_markets(rows) if m == '1x2'][0]
    assert one[0] == 'Home' and one[1]['confidence_source'] == 'model'
    assert one[1]['confidence'] == pytest.approx(one[1]['model_confidence'])
    assert one[1]['market_confidence'] < one[1]['confidence']          # market shown for comparison
    assert tier_hit_rate('TINGGI', 'model') < tier_hit_rate('TINGGI', 'sharp')
    assert source_label('model') == 'Model DC + pasar'
    assert source_label('model', national=True) == 'Model tim nasional + pasar'
    # With a sharp price the sharp view wins, the model view is kept for display.
    fair = {('1x2', 'home', None): .46, ('1x2', 'draw', None): .28, ('1x2', 'away', None): .26}
    rows = SCAN['price_fixture'](dist, book(), gated=False, reference_fair=fair, model_confidence=True)
    home = [o for m, label, o in rows if m == '1x2' and label == 'Home'][0]
    assert home['confidence_source'] == 'sharp' and home['model_confidence'] > .5


# --- Oct 18: storage size + big-league priority ---
from football_formula_engine.league_tiers import league_tier
from football_formula_engine.confidence import compact_options


def test_league_tiers():
    assert league_tier('England. Premier League', 'E0') == 1
    assert league_tier('UEFA Champions League') == 1
    assert league_tier('Netherlands. Eredivisie', 'N1') == 2
    assert league_tier('Copa Libertadores') == 2
    assert league_tier('World Cup Qualification. Europe', national=True) == 2
    assert league_tier('Algeria. Ligue 2') == 3
    assert league_tier('Germany. 3. Liga', 'D3') == 3
    assert league_tier('England. Premier League Cup U21') == 3


def test_compact_options_keeps_main_lines_and_value_only():
    dist = build_score_matrix(1.5, 1.0, 0.0)
    mk = dict(book(), odds_btts={'yes': 1.9, 'no': 1.9})
    mk['odds_ou'] = {str(l): {'9': o, '10': u} for l, o, u in
                     ((1.5, 1.25, 3.9), (2.0, 1.45, 2.7), (2.5, 1.95, 1.88), (3.0, 2.6, 1.48), (3.5, 3.3, 1.32))}
    rows = SCAN['price_fixture'](dist, mk, gated=False, reference_fair={})
    kept = compact_options(rows)
    ou_lines = {o['line_quarters'] for m, _, o in kept if m == 'ou'}
    assert ou_lines == {10}
    assert sum(1 for m, _, _ in kept if m == '1x2') == 3 and sum(1 for m, _, _ in kept if m == 'btts') == 2
    assert len(kept) < len(rows)


def test_prune_keeps_recent_and_referenced_quotes(tmp_path):
    import importlib.util, time as _t
    spec = importlib.util.spec_from_file_location('prune', ROOT / 'scripts/fc-prune-data.py')
    prune = importlib.util.module_from_spec(spec); spec.loader.exec_module(prune)
    db = tmp_path / 'q.db'
    j = QuoteJournal(db)
    now = _t.time()
    old = {'match_id': 'old', 'start_ts': now - 40 * 86400}
    ref = {'match_id': 'ref', 'start_ts': now - 40 * 86400}
    new = {'match_id': 'new', 'start_ts': now + 3600}
    mk = {'odds_1x2': {1: 2.0, 2: 3.4, 3: 3.8}}
    j.record(old, mk, {}, captured_at=old['start_ts'] - 600)
    r = j.record(ref, mk, {}, captured_at=ref['start_ts'] - 600)
    j.record(new, mk, {}, captured_at=now - 60)
    with j.connect() as c:   # research decision referencing the old 'ref' observation
        c.execute('INSERT INTO research_decisions VALUES (?, ?, ?)',
                  ('ref', 'p', json.dumps({'observation_id': r['artifact_id']})))
    dry = prune.prune_journal(db, now - 21 * 86400, apply=False, backup=False)
    assert dry['observations'] == 3 and dry['kept'] == 2 and dry['status'] == 'dry_run'
    done = prune.prune_journal(db, now - 21 * 86400, apply=True, backup=False)
    assert done['status'] == 'pruned'
    j2 = QuoteJournal(db)
    with j2.connect() as c:
        ids = {row[0] for row in c.execute('SELECT fixture_id FROM observations')}
        assert ids == {'ref', 'new'}
        assert c.execute('SELECT COUNT(*) FROM research_decisions').fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError if False else Exception):
            c.execute("DELETE FROM observations")      # immutability triggers survive


def test_compact_raw_keeps_identity_and_digest():
    raw = SCAN['compact_raw']({'I': 5, 'S': 10, 'O1': 'A', 'O2': 'B', 'L': 'X', 'Value': [1] * 5000})
    assert raw['I'] == 5 and len(raw['raw_sha256']) == 64 and raw['raw_bytes'] > 10000
    assert 'Value' not in raw


def test_juventus_case_coin_flip_markets_are_balanced_and_scenario_explains_ah():
    """1X2 'Juventus' + AH 'Lazio +1' case (18 Oct): both likelier sides, not a contradiction."""
    from football_formula_engine.confidence import score_scenario
    from football_formula_engine.market_goals import infer_market_goals
    mk = {'odds_1x2': {1: 1.61, 2: 3.9, 3: 5.6}, 'odds_ou': {'2.5': {'9': 1.96, '10': 1.86}},
          'odds_ah': {'home': [(-1.0, 2.05)], 'away': [(1.0, 1.85)]}, 'odds_btts': {'yes': 1.95, 'no': 1.82}}
    g = infer_market_goals(mk)
    dist = build_score_matrix(g['home'], g['away'], 0.0)
    shown = {m: o for m, _, o in display_markets(SCAN['price_fixture'](dist, mk, gated=False, reference_fair={}))}
    assert shown['1x2']['side'] == 'home' and shown['1x2']['display_status'] == 'pick'
    # Lazio +1 (main line) is ~54%, a coin flip; no alternative line is offered here.
    assert shown['ah']['side'] == 'away' and shown['ah']['display_status'] == 'no_lean'
    assert shown['btts']['display_status'] == 'no_lean'
    s = score_scenario(dist)
    assert s['favourite'] == 'home'
    assert abs(s['home_win'] - (s['home_by1'] + s['home_by2_plus'])) < 1e-3
    assert 0.2 < s['home_by1'] < 0.3 and 0.3 < s['home_by2_plus'] < 0.4


def test_coin_flip_main_line_switches_to_clear_alternative_line():
    from football_formula_engine.market_goals import infer_market_goals
    mk = {'odds_1x2': {1: 1.61, 2: 3.9, 3: 5.6}, 'odds_ou': {'2.5': {'9': 1.96, '10': 1.86}},
          'odds_ah': {'home': [(-1.0, 2.05), (-1.5, 2.75), (-0.5, 1.62)],
                      'away': [(1.0, 1.85), (1.5, 1.45), (0.5, 2.35)]},
          'odds_btts': {'yes': 1.95, 'no': 1.82}}
    g = infer_market_goals(mk)
    dist = build_score_matrix(g['home'], g['away'], 0.0)
    rows = SCAN['price_fixture'](dist, mk, gated=False, reference_fair={})
    ah = {m: o for m, _, o in display_markets(rows)}['ah']
    assert ah['display_status'] == 'alt_line'
    assert ah['confidence'] >= 0.60 and ah['odds'] >= 1.40
    assert ah['main_line_confidence'] < 0.55
    assert (ah['side'], ah['line_quarters']) == ('away', 6)     # Lazio +1.5
    kept = compact_options(rows)
    assert any(o.get('display_status') == 'alt_line' for _, _, o in kept)
