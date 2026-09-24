import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('fc_preflight', ROOT / 'scripts/fc-preflight-24h.py')
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def fixture(league, home='Arsenal', away='Chelsea', start=1000):
    return {'info': {'match_id': '1', 'league': league, 'home': home,
                     'away': away, 'start_ts': start}}


def test_unsupported_slate_has_no_pick_path():
    result = preflight.audit([fixture('UEFA Nations League. Team vs Player')], now=0)
    assert result['verdict'] == 'NO_SUPPORTED_LEAGUE_24H'
    assert result['modelable_team_fixtures'] == 0
    assert result['value_pick_status'] == 'NO_MODELABLE_FIXTURES'


def test_supported_teams_are_only_potential_until_odds_checked(monkeypatch):
    monkeypatch.setattr(preflight.scan, 'csv_teams', lambda _code: {'Arsenal', 'Chelsea'})
    result = preflight.audit([fixture('England. Premier League')], now=0)
    assert result['verdict'] == 'MODELABLE_FIXTURES_24H'
    assert result['modelable_team_fixtures'] == 1
    assert result['value_pick_status'] == 'NOT_EVALUATED_NO_LIVE_ODDS'


def test_extended_window_keeps_24h_distinction():
    rows = [fixture('UEFA Nations League. Team vs Player', start=36 * 3600)]
    assert preflight.audit(rows, now=0)['verdict'] == 'NO_FIXTURES_24H'
    assert preflight.audit(rows, now=0, hours=72)['verdict'] == 'NO_SUPPORTED_LEAGUE_72H'
