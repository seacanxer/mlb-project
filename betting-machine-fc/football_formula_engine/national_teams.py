"""Point-in-time men's senior international results and exact fixture identity."""
import csv
import hashlib
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .data import NormalizedMatch, stable_id

SOURCE_URL = 'https://github.com/martj42/international_results/blob/master/results.csv'
SOURCE_NAME = 'martj42/international_results/results.csv'
MODEL_CODE = 'INT_MEN'
SENIOR_COMPETITIONS = frozenset({
    'UEFA Nations League', 'Africa Cup of Nations', 'CONCACAF Nations League',
    'Friendlies. National Teams', 'Arabian Gulf Cup',
})
TEAM_ALIASES = {'Comoros': 'Comoro Islands', 'DR Congo': 'DR Congo',
                'Congo DR': 'DR Congo', 'South Korea': 'South Korea',
                'Czechia': 'Czech Republic', 'Türkiye': 'Turkey',
                'Curacao': 'Curaçao'}
MIN_TEAM_MATCHES = 12
HISTORY_START = '2023-01-01'


def canonical_team(name):
    return TEAM_ALIASES.get((name or '').strip(), (name or '').strip())


def senior_competition(league):
    return (league or '').strip() in SENIOR_COMPETITIONS


def load_results(path, cutoff_utc, *, start_date=HISTORY_START):
    """Only completed games available before cutoff; neutral flags stay explicit."""
    matches, neutral_ids, counts = [], set(), Counter()
    latest_result = 0
    with Path(path).open(newline='', encoding='utf-8-sig') as handle:
        for row_number, row in enumerate(csv.DictReader(handle), 2):
            date = row.get('date') or ''
            if date < start_date:
                continue
            try:
                played = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                available_at = int((played + timedelta(days=1)).timestamp())
                home_goals, away_goals = int(row['home_score']), int(row['away_score'])
            except (ValueError, KeyError):
                continue
            if available_at > cutoff_utc or min(home_goals, away_goals) < 0:
                continue
            home, away = canonical_team(row.get('home_team')), canonical_team(row.get('away_team'))
            if not home or not away or home == away:
                continue
            fixture_id = 'intl-' + stable_id(date, home, away, str(row_number))
            raw = '|'.join(str(row.get(key, '')) for key in ('date', 'home_team', 'away_team',
                                                            'home_score', 'away_score', 'neutral'))
            matches.append(NormalizedMatch(
                fixture_id=fixture_id, competition_id=MODEL_CODE, season=date[:4],
                home_team_id='intl-team-' + stable_id(home),
                away_team_id='intl-team-' + stable_id(away),
                home_team_name=home, away_team_name=away,
                kickoff_utc=int(played.timestamp()), result_status='final',
                home_goals=home_goals, away_goals=away_goals,
                result_available_at_utc=available_at,
                result_availability_basis='next_calendar_day_utc',
                source='martj42/international_results', source_file=str(path),
                source_row=row_number, raw_sha256=hashlib.sha256(raw.encode()).hexdigest()))
            if row.get('neutral', '').upper() == 'TRUE':
                neutral_ids.add(fixture_id)
            counts[home] += 1
            counts[away] += 1
            latest_result = max(latest_result, available_at)
    return matches, neutral_ids, counts, latest_result


def resolve_fixture(home, away, counts):
    home_name, away_name = canonical_team(home), canonical_team(away)
    if home_name == away_name or min(counts.get(home_name, 0), counts.get(away_name, 0)) < MIN_TEAM_MATCHES:
        return None
    return home_name, away_name


def nonneutral_baseline_coverage(matches, neutral_ids, minimum_side_matches=5):
    """Ratio baseline needs observed home and away games for both teams."""
    home, away = Counter(), Counter()
    training = []
    for match in matches:
        if match.fixture_id in neutral_ids:
            continue
        training.append(match)
        home[match.home_team_name] += 1
        away[match.away_team_name] += 1
    counts = {name: home[name] + away[name] for name in home.keys() | away.keys()
              if home[name] >= minimum_side_matches and away[name] >= minimum_side_matches}
    return training, counts
