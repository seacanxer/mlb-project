"""Score-feed lanes: FotMob day feed, ESPN scoreboard and training-file priority."""
import importlib.util
import json
from pathlib import Path

import pytest

from football_formula_engine.data import load_football_data_csv
from football_formula_engine.day_feed import FeedMatch, parse_day
from football_formula_engine.espn_feed import parse_day as parse_espn_day
from football_formula_engine.leagues import (LEAGUES, LEAGUE_BY_NAME,
                                             current_season_for, matches_feed_name,
                                             season_label)

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('scan_dayfeed_tests', ROOT / 'scripts/fc-scan-live.py')
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)

DAY_FEED_XML = b'''<?xml version="1.0" encoding="UTF-8"?>
<live>
  <exmatches>
    <league id="938215" name="J. League 2" ccode="JPN" pl="10">
      <match id="101" hTeam="A Team" aTeam="B Team" hScore="2" aScore="1"
             time="19.09.2026 12:00" Status="F"/>
      <match id="102" hTeam="C Team" aTeam="D Team" time="19.09.2026 14:00" Status="N"/>
      <match id="103" hTeam="E Team" aTeam="F Team" hScore="x" aScore="0"
             time="19.09.2026 16:00" Status="F"/>
      <match id="104" hTeam="G Team" aTeam="G Team" hScore="1" aScore="0"
             time="19.09.2026 18:00" Status="F"/>
    </league>
  </exmatches>
</live>'''


def test_day_feed_parses_finished_scores_only():
    matches = parse_day(DAY_FEED_XML, day='20260919')
    assert len(matches) == 1
    match = matches[0]
    assert match.ccode == 'JPN'
    assert (match.home, match.away, match.home_goals, match.away_goals) == (
        'A Team', 'B Team', 2, 1)
    assert match.kickoff_local.strftime('%d/%m/%Y %H:%M') == '19/09/2026 12:00'


def test_feed_name_mapping_ignores_sibling_competitions():
    assert matches_feed_name('MEX1', ccode='MEX', name='Liga MX Apertura')
    assert not matches_feed_name('MEX1', ccode='MEX', name='Liga MX Femenil Apertura')
    assert matches_feed_name('E0', ccode='ENG', name='Premier League')
    assert not matches_feed_name('E0', ccode='ENG', name='Premier League 2')
    assert matches_feed_name('EPL2', ccode='ENG', name='Premier League 2')
    assert not matches_feed_name('E0', ccode='SCO', name='Premier League')
    assert matches_feed_name('NOR3', ccode='NOR', name='Norsk Tipping-ligaen Avd. 1')
    assert matches_feed_name('SC1', ccode='SCO', name='Championship',
                             pl_name='Championship')


def test_season_label_follows_each_league_calendar():
    from datetime import date
    assert season_label(date(2026, 9, 1), 7) == '2627'
    assert season_label(date(2026, 6, 1), 7) == '2526'
    assert season_label(date(2026, 3, 1), 1) == '2627'
    assert season_label(date(2026, 1, 15), 1) == '2627'
    assert season_label(date(2026, 3, 1), 4) == '2526'
    assert season_label(date(2026, 9, 1), 4) == '2627'


def test_current_season_for_uses_league_calendar():
    import time
    now = time.time()
    assert current_season_for('E0', now) == '2627'
    assert current_season_for('J2', now) == '2627'
    assert current_season_for('UNKNOWN', now) == current_season_for('E0', now)


def test_registry_keeps_legacy_shape_and_names():
    assert LEAGUES['E0'][1] == 'Europe/London'
    assert LEAGUES['E0'].source == 'football-data'
    assert LEAGUES['J2'].source == 'dayfeed'
    assert LEAGUE_BY_NAME['japan. j-league division 2'] == 'J2'
    assert LEAGUE_BY_NAME['netherlands. eerste divisie'] == 'N2'
    assert 'albacete balompie' in scan.TEAM_ALIASES


def test_dayfeed_csv_carries_source_and_no_quotes(tmp_path):
    path = tmp_path / 'X1_2627_dayfeed.csv'
    path.write_text('Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG\n'
                    'X1,19/09/2026,12:00,A Team,B Team,2,1\n', encoding='utf-8')
    matches, quotes = load_football_data_csv(path, competition_id='X1', season='2627',
                                             timezone_name='UTC', source='fotmob-dayfeed')
    assert len(matches) == 1 and not quotes
    assert matches[0].source == 'fotmob-dayfeed'
    assert matches[0].result_status == 'final'


def test_training_file_lane_priority(tmp_path, monkeypatch):
    monkeypatch.setattr(scan, 'FC_DIR', str(tmp_path))
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'E0_2627_dayfeed.csv').write_text('dayfeed')
    assert scan.training_files('E0')[-1][0] == 'E0_2627_dayfeed.csv'
    (data / 'E0_2627.csv').write_text('archive')
    assert scan.training_files('E0')[-1][0] == 'E0_2627.csv'
    (data / 'E0_2627_live_scores.csv').write_text('live')
    assert scan.training_files('E0')[-1][0] == 'E0_2627_live_scores.csv'
    # Registered prior seasons survive the current-season override.
    files = scan.training_files('E0')
    assert ('E0_2425.csv', '2425') in files
    assert ('E0_2526.csv', '2526') in files
    assert [season for _file, season in files].count('2627') == 1


def test_score_feed_leagues_skip_football_data_refresh(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(scan, 'FC_DIR', str(tmp_path))
    monkeypatch.delenv('FC_SECOND_MAPPING_PATH', raising=False)
    monkeypatch.delenv('FC_QUOTES_DB', raising=False)
    monkeypatch.setattr(scan, 'refresh_scores', lambda *a, **k: called.append(a) or
                        {'status': 'cached'})
    monkeypatch.setattr(scan, 'MODEL_DATA_INFO', {})
    (tmp_path / 'matches_detailed.json').write_text('[]')
    monkeypatch.setattr(scan.sc, 'list_matches_paginated', lambda **kwargs: [
        {'I': '1', 'S': 1789903600, 'O1': 'Home', 'O2': 'Away',
         'L': 'Japan. J-League Division 2'}])
    monkeypatch.setattr(scan.time, 'time', lambda: 1789900000.0)
    monkeypatch.setattr(scan.time, 'sleep', lambda _: None)
    monkeypatch.setattr(scan, 'load_model', lambda *a, **k: None)
    assert scan.main() == 0
    assert called == []
    refresh = scan.MODEL_DATA_INFO['J2']['refresh']
    assert refresh == {'status': 'skipped', 'season': '2627',
                       'reason': 'NON_FOOTBALL_DATA_SOURCE'}


def test_espn_scoreboard_parses_posted_results():
    payload = json.dumps({'events': [{
        'id': '401880253',
        'date': '2026-09-19T11:30:00Z',
        'status': {'type': {'state': 'post'}},
        'competitions': [{'competitors': [
            {'homeAway': 'home', 'score': '3',
             'team': {'displayName': 'Cardiff City'}},
            {'homeAway': 'away', 'score': '2',
             'team': {'displayName': 'Charlton Athletic'}}]}]},
        {'id': '401880254',
         'date': '2026-09-19T15:00:00Z',
         'status': {'type': {'state': 'pre'}},
         'competitions': [{'competitors': []}]}]})
    matches = parse_espn_day(payload, slug='eng.trophy')
    assert len(matches) == 1
    assert (matches[0].home, matches[0].away) == ('Cardiff City', 'Charlton Athletic')
    assert matches[0].kickoff_utc.isoformat() == '2026-09-19T11:30:00+00:00'
