import json
from datetime import date
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[2]


def test_national_ingestion_is_scoped_and_retry_does_not_refetch(tmp_path, capsys):
    module = runpy.run_path(str(ROOT / 'scripts/fc-fetch-match-stats.py'))
    run = module['run']
    scope = run.__globals__
    scope['DATA_DIR'] = str(tmp_path)
    base = {'match_id': '1', 'home': 'Spain', 'away': 'Croatia',
            'home_goals': '2', 'away_goals': '1', 'kickoff_local': '20:45'}
    scope['finished_matches'] = lambda day: [
        {**base, 'league': 'UEFA Nations League A Grp. 1'},
        {**base, 'match_id': '2', 'league': 'National League'},
        {**base, 'match_id': '3', 'league': 'UEFA Nations League Women'},
        {**base, 'match_id': '4', 'league': 'UEFA Nations League Final'}]
    fetched = []
    def stats(mid):
        fetched.append(mid)
        return {'corners': [7, 3]}
    scope['match_stats'] = stats
    for _ in range(2):
        assert run('INT_MEN', [], 1, date(2026, 10, 5), 2) == 0
    assert fetched == ['1']
    assert json.loads(capsys.readouterr().out.splitlines()[-1])['rows'] == 1


def test_feed_failure_is_reported(tmp_path, capsys):
    module = runpy.run_path(str(ROOT / 'scripts/fc-fetch-match-stats.py'))
    run = module['run']
    run.__globals__['DATA_DIR'] = str(tmp_path)
    def broken(day):
        raise OSError('offline')
    run.__globals__['finished_matches'] = broken
    assert run('INT_MEN', [], 1, date(2026, 10, 5), 1) == 1
    assert json.loads(capsys.readouterr().out)['feed_failed'] == 1


def test_domestic_stats_require_correct_country_and_competition():
    match = runpy.run_path(str(ROOT / 'scripts/fc-fetch-match-stats.py'))['competition_matches']
    assert match({'league': 'Bundesliga', 'ccode': 'GER'}, 'D1', ['Bundesliga'])
    assert not match({'league': 'Bundesliga', 'ccode': 'AUT'}, 'D1', ['Bundesliga'])
    assert not match({'league': '2. Bundesliga', 'ccode': 'GER'}, 'D1', ['Bundesliga'])
    assert not match({'league': 'Bundesliga'}, 'D1', ['Bundesliga'])
