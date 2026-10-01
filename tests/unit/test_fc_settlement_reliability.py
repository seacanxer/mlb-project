from datetime import date
import json
from pathlib import Path
import runpy
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))

import scores_espn
import scores_flashscore
import scores_fotmob


def test_flashscore_offsets_include_old_backlog_dates_without_future_guessing():
    today = date(2026, 10, 1)
    assert scores_flashscore._requested_offsets(0, ['2026-09-10', 'invalid'], today) == [-21]
    assert scores_flashscore._requested_offsets(3, ['2026-09-10'], today) == [0, -1, -2, -21]


def test_fotmob_fetches_a_requested_historical_date(monkeypatch):
    xml = (b'<match id="42" hTeam="Home FC" aTeam="Away FC" hScore="2" '
           b'aScore="0" Status="F"></match>')

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return xml

    requested = []
    monkeypatch.setattr(scores_fotmob.urllib.request, 'urlopen',
                        lambda req, timeout: (requested.append(req.full_url) or Response()))
    result = scores_fotmob.fetch_recent_results(
        days=0, use_cache=False, target_dates=['2026-09-10'])
    assert requested == ['https://apigw.fotmob.com/matches?date=20260910']
    row = scores_fotmob.find_result('Home FC', 'Away FC', scores_fotmob.build_lookup(result), date(2026, 9, 10))
    assert row and (row['home_score'], row['away_score']) == (2, 0)


def test_espn_backfill_scopes_league_and_uses_homeaway_identity(monkeypatch):
    calls = []
    response = {
        'leagues': [{'name': 'Premier League'}],
        'events': [{'status': {'type': {'name': 'STATUS_FULL_TIME'}},
                    'competitions': [{'id': 'event-1', 'competitors': [
                        {'homeAway': 'away', 'score': '1', 'team': {'displayName': 'Away FC'}},
                        {'homeAway': 'home', 'score': '3', 'team': {'displayName': 'Home FC'}},
                    ]}]}],
    }
    monkeypatch.setattr(scores_espn, '_fetch_day',
                        lambda slug, day: (calls.append((slug, day)) or response))
    rows = scores_espn.fetch_recent_results(days=0, use_cache=False,
        target_dates=['2026-09-10'], leagues=['England. Premier League'])
    assert calls == [('eng.1', '20260910')]
    assert rows[0]['home'] == 'Home FC' and rows[0]['away'] == 'Away FC'
    assert (rows[0]['home_goals'], rows[0]['away_goals']) == (3, 1)


def test_espn_skips_unmapped_leagues_instead_of_fanning_out_to_every_slug(monkeypatch):
    monkeypatch.setattr(scores_espn, '_fetch_day', lambda *_args: (_ for _ in ()).throw(AssertionError()))
    assert scores_espn.fetch_recent_results(days=0, use_cache=False,
        target_dates=['2026-09-10'], leagues=['Finland. Kolmonen']) == []


def test_espn_resolves_exact_league_date_pairs(monkeypatch):
    calls = []
    monkeypatch.setattr(scores_espn, '_fetch_day',
                        lambda slug, day: (calls.append((slug, day)) or None))
    scores_espn.fetch_recent_results(days=0, use_cache=False,
        target_dates=['2026-09-10', '2026-09-11'],
        league_dates=[('2026-09-10', 'England. Premier League')])
    assert calls == [('eng.1', '20260910')]


def test_result_feed_fanout_keeps_one_provider_failure_isolated(monkeypatch):
    namespace = runpy.run_path(str(ROOT / 'scripts' / 'fc-settle-live.py'))
    monkeypatch.setattr(namespace['scores_flashscore'], 'fetch_recent_results',
                        lambda **_kwargs: {'fs': [{'home': 'A', 'away': 'B'}]})
    monkeypatch.setattr(namespace['scores_alt'], 'fetch_recent_results',
                        lambda **_kwargs: (_ for _ in ()).throw(TimeoutError('offline')))
    monkeypatch.setattr(namespace['scores_fotmob'], 'fetch_recent_results', lambda **_kwargs: {})
    monkeypatch.setattr(namespace['scores_espn'], 'fetch_recent_results', lambda **_kwargs: [])
    result = namespace['fetch_result_feeds'](['2026-09-10'], ['England. Premier League'])
    assert result['flashscore']['fs'][0] == {'home': 'A', 'away': 'B'}
    assert result['alt'] == {}
    assert result['fotmob'] == {} and result['espn'] == []


def test_shared_process_lock_rejects_overlapping_api_or_cron_runs(monkeypatch, tmp_path, capsys):
    namespace = runpy.run_path(str(ROOT / 'scripts' / 'fc-settle-live.py'))
    monkeypatch.setenv('FC_SETTLE_LOCK_PATH', str(tmp_path / 'settle.lock'))
    entered, release = threading.Event(), threading.Event()

    @namespace['serialize_settlement']
    def work():
        entered.set()
        assert release.wait(3)
        return 7

    first_result = []
    thread = threading.Thread(target=lambda: first_result.append(work()))
    thread.start()
    assert entered.wait(3)
    assert work() == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'busy'
    release.set()
    thread.join(3)
    assert first_result == [7]
