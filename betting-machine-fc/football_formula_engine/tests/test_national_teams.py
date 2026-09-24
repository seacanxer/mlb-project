import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from football_formula_engine.national_teams import (load_results, resolve_fixture,
    senior_competition)

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / 'betting-machine-fc/data/international_results.csv'
META = ROOT / 'betting-machine-fc/data/international_results.source.json'


def test_source_integrity_and_scope():
    expected = json.loads(META.read_text(encoding='utf-8'))['sha256']
    assert hashlib.sha256(DATA.read_bytes()).hexdigest() == expected
    assert senior_competition('UEFA Nations League')
    assert not senior_competition('UEFA Nations League. Team vs Player')
    assert not senior_competition('Africa Cup of Nations U20')


def test_results_respect_cutoff_and_neutral_flag(tmp_path):
    source = tmp_path / 'results.csv'
    with source.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['date', 'home_team', 'away_team',
            'home_score', 'away_score', 'neutral'])
        writer.writeheader()
        writer.writerow(dict(date='2026-09-20', home_team='Japan', away_team='Uruguay',
                             home_score=2, away_score=1, neutral='TRUE'))
        writer.writerow(dict(date='2026-09-21', home_team='Japan', away_team='Iran',
                             home_score=1, away_score=0, neutral='FALSE'))
    cutoff = int(datetime(2026, 9, 21, tzinfo=timezone.utc).timestamp())
    matches, neutral, counts, latest = load_results(source, cutoff)
    assert len(matches) == 1
    assert matches[0].fixture_id in neutral
    assert counts['Japan'] == 1
    assert latest == cutoff


def test_exact_team_resolution_with_verified_alias():
    assert resolve_fixture('Costa Rica', 'Curacao', {'Costa Rica': 20, 'Curaçao': 20}) == ('Costa Rica', 'Curaçao')
    assert resolve_fixture('Costa Rica U20', 'Curacao', {'Costa Rica': 20, 'Curaçao': 20}) is None
