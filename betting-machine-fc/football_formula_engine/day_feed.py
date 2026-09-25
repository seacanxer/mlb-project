"""FotMob day-feed score ingestion (finished matches only, no odds).

The day feed is a single request per calendar date that lists every league
FotMob knows about for that date.  Raw responses are cached on disk so a
season rebuild is repeatable without re-hitting the upstream API.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import io
import os
from pathlib import Path
import time
import urllib.request
import xml.etree.ElementTree as ET

FEED_URL = 'https://apigw.fotmob.com/matches?date={date}'
USER_AGENT = 'Mozilla/5.0 (compatible; fc-dayfeed/1; +https://localhost)'
MAX_BYTES = 6_000_000
MAX_ATTEMPTS = 4
FINISHED_STATUS = 'F'


@dataclass(frozen=True)
class FeedMatch:
    source_id: str
    ccode: str
    league_id: str
    league_name: str
    pl_name: str
    home: str
    away: str
    home_goals: int
    away_goals: int
    status: str
    home_id: str = ''
    away_id: str = ''
    kickoff_local: datetime | None = None
    kickoff_utc: datetime | None = None


def cache_path(cache_dir, day):
    return Path(cache_dir) / f'{day}.xml'


def fetch_day(day, *, cache_dir, refresh=False, delay=0.0, timeout=30, opener=None):
    """Fetch (or read) one ``YYYYMMDD`` day feed; returns the payload path."""
    if len(str(day)) != 8 or not str(day).isdigit():
        raise ValueError(f'Invalid day {day!r}')
    target = cache_path(cache_dir, day)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not refresh:
        return target
    if delay:
        time.sleep(delay)
    url = FEED_URL.format(date=day)
    last_error = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            request = urllib.request.Request(url, headers={
                'User-Agent': USER_AGENT, 'Accept-Encoding': 'gzip',
                'Accept': 'application/xml,text/xml,*/*'})
            open_url = opener or urllib.request.urlopen
            with open_url(request, timeout=timeout) as response:
                payload = response.read(MAX_BYTES + 1)
            if len(payload) > MAX_BYTES:
                raise ValueError('Day feed exceeds bounded download size')
            if payload[:2] == b'\x1f\x8b':
                payload = gzip.GzipFile(fileobj=io.BytesIO(payload)).read()
            if b'<live>' not in payload[:2048]:
                raise ValueError('Day feed is not a FotMob matches document')
            tmp = target.with_suffix('.xml.tmp')
            tmp.write_bytes(payload)
            os.replace(tmp, target)
            return target
        except Exception as exc:  # bounded retries with backoff
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f'FotMob day feed {day} failed: {last_error}')


def fetch_range(start, end, *, cache_dir, refresh=False, delay=0.0, max_days=None,
                progress=None, opener=None):
    """Fetch every day in ``[start, end]`` (``datetime.date`` values)."""
    from datetime import timedelta
    fetched, skipped, failures = [], [], []
    day = start
    index = 0
    while day <= end:
        if max_days is not None and index >= max_days:
            break
        key = day.strftime('%Y%m%d')
        path = cache_path(cache_dir, key)
        existed = path.exists()
        try:
            fetch_day(key, cache_dir=cache_dir, refresh=refresh and existed,
                      delay=delay, opener=opener)
        except Exception as exc:
            failures.append({'day': key, 'reason': str(exc)})
        else:
            (skipped if existed and not refresh else fetched).append(key)
        if progress:
            progress(key, existed)
        day += timedelta(days=1)
        index += 1
    return {'fetched': fetched, 'cached': skipped, 'failures': failures}


def parse_day(payload, *, day=None):
    """Parse one cached day feed into finished :class:`FeedMatch` rows."""
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError(f'Unparseable day feed {day}: {exc}') from exc
    matches = []
    for league in root.iter('league'):
        ccode = league.get('ccode') or ''
        league_id = league.get('id') or ''
        league_name = league.get('name') or ''
        pl_name = league.get('plName') or ''
        for node in league.findall('match'):
            status = node.get('Status') or ''
            if status != FINISHED_STATUS:
                continue
            home, away = node.get('hTeam'), node.get('aTeam')
            if not home or not away or home == away:
                continue
            goals = _goals(node.get('hScore'), node.get('aScore'))
            if goals is None:
                continue
            kickoff = _kickoff(node.get('time'))
            if kickoff is None:
                continue
            matches.append(FeedMatch(
                source_id=node.get('id') or '', ccode=ccode, league_id=league_id,
                league_name=league_name, pl_name=pl_name, home=home, away=away,
                home_goals=goals[0], away_goals=goals[1], status=status,
                home_id=node.get('hId') or '', away_id=node.get('aId') or '',
                kickoff_local=kickoff))
    return matches


def parse_cache(cache_dir, days=None):
    """Parse every cached day (or a specific list of ``YYYYMMDD`` days)."""
    directory = Path(cache_dir)
    if days is None:
        days = sorted(p.stem for p in directory.glob('*.xml')) if directory.exists() else []
    out = []
    for day in days:
        path = cache_path(cache_dir, day)
        if path.exists():
            out.extend(parse_day(path.read_bytes(), day=day))
    return out


def _goals(home, away):
    try:
        hg, ag = int(home), int(away)
    except (TypeError, ValueError):
        return None
    if hg < 0 or ag < 0:
        return None
    return hg, ag


def _kickoff(value):
    if not value:
        return None
    for pattern in ('%d.%m.%Y %H:%M', '%d.%m.%Y %H:%M:%S'):
        try:
            return datetime.strptime(value.strip(), pattern)
        except ValueError:
            continue
    return None


def day_keys(start, end):
    from datetime import timedelta
    keys, day = [], start
    while day <= end:
        keys.append(day.strftime('%Y%m%d'))
        day += timedelta(days=1)
    return keys


def retrieved_at(path):
    return int(Path(path).stat().st_mtime)


def utc_now():
    return int(time.time())
