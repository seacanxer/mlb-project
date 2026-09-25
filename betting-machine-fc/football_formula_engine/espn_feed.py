"""ESPN scoreboard ingestion (finished matches only, no odds).

Used as a second score source for leagues the FotMob day feed does not carry.
One request per ``(slug, day)``; responses are cached like the FotMob feed.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import urllib.request

SCOREBOARD_URL = ('https://site.api.espn.com/apis/site/v2/sports/soccer/'
                  '{slug}/scoreboard?dates={day}&limit=200')
USER_AGENT = 'Mozilla/5.0 (compatible; fc-dayfeed/1; +https://localhost)'
MAX_BYTES = 12_000_000
MAX_ATTEMPTS = 4
FINISHED_STATES = frozenset({'post'})


@dataclass(frozen=True)
class EspnMatch:
    source_id: str
    slug: str
    home: str
    away: str
    home_goals: int
    away_goals: int
    kickoff_utc: datetime


def cache_path(cache_dir, slug, day):
    return Path(cache_dir) / slug.replace('.', '_') / f'{day}.json'


def fetch_day(slug, day, *, cache_dir, refresh=False, delay=0.0, timeout=30, opener=None):
    if len(str(day)) != 8 or not str(day).isdigit():
        raise ValueError(f'Invalid day {day!r}')
    target = cache_path(cache_dir, slug, day)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not refresh:
        return target
    if delay:
        time.sleep(delay)
    url = SCOREBOARD_URL.format(slug=slug, day=day)
    last_error = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            open_url = opener or urllib.request.urlopen
            with open_url(request, timeout=timeout) as response:
                payload = response.read(MAX_BYTES + 1)
            if len(payload) > MAX_BYTES:
                raise ValueError('Scoreboard exceeds bounded download size')
            data = json.loads(payload)
            if not isinstance(data.get('events'), list):
                raise ValueError('Scoreboard payload has no event list')
            tmp = target.with_suffix('.json.tmp')
            tmp.write_text(payload.decode('utf-8'), encoding='utf-8')
            os.replace(tmp, target)
            return target
        except Exception as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f'ESPN scoreboard {slug} {day} failed: {last_error}')


def parse_day(payload, *, slug, day=None):
    """Parse one cached scoreboard into finished :class:`EspnMatch` rows."""
    try:
        data = json.loads(payload)
    except ValueError as exc:
        raise ValueError(f'Unparseable scoreboard {slug} {day}: {exc}') from exc
    out = []
    for event in data.get('events') or []:
        status = ((event.get('status') or {}).get('type') or {})
        if (status.get('state') or '').lower() not in FINISHED_STATES:
            continue
        kickoff = _kickoff(event.get('date'))
        if kickoff is None:
            continue
        competitors = {}
        for competition in event.get('competitions') or []:
            for competitor in competition.get('competitors') or []:
                side = competitor.get('homeAway')
                team = (competitor.get('team') or {}).get('displayName')
                score = competitor.get('score')
                if side in ('home', 'away') and team:
                    competitors[side] = (team, score)
        if set(competitors) != {'home', 'away'}:
            continue
        home, home_score = competitors['home']
        away, away_score = competitors['away']
        goals = _goals(home_score, away_score)
        if goals is None or home == away:
            continue
        out.append(EspnMatch(source_id=str(event.get('id') or ''), slug=slug,
                             home=home, away=away, home_goals=goals[0],
                             away_goals=goals[1], kickoff_utc=kickoff))
    return out


def parse_cache(cache_dir, slug):
    """Parse every cached scoreboard day for one slug."""
    directory = Path(cache_dir) / slug.replace('.', '_')
    out = []
    if not directory.exists():
        return out
    for path in sorted(directory.glob('*.json')):
        out.extend(parse_day(path.read_bytes(), slug=slug, day=path.stem))
    return out


def _kickoff(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _goals(home, away):
    try:
        hg, ag = int(str(home).strip()), int(str(away).strip())
    except (TypeError, ValueError):
        return None
    if hg < 0 or ag < 0:
        return None
    return hg, ag
