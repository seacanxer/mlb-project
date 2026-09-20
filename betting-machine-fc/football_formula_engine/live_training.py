"""Refresh current-season scores without replacing valid data on failure."""
import csv
import hashlib
import io
import json
from pathlib import Path
from datetime import datetime, timezone
import urllib.request


def current_season(now):
    date = datetime.fromtimestamp(now, timezone.utc)
    year = date.year if date.month >= 7 else date.year - 1
    return f'{year % 100:02d}{(year + 1) % 100:02d}'


def refresh_scores(code, data_dir, now, *, max_age=21600):
    season = current_season(now)
    target = Path(data_dir) / f'{code}_{season}_live_scores.csv'
    if target.exists() and 0 <= now - target.stat().st_mtime < max_age:
        return {'status': 'cached', 'season': season}
    url = f'https://www.football-data.co.uk/mmz4281/{season}/{code}.csv'
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = response.read(8_000_001)
        if len(payload) > 8_000_000:
            raise ValueError('CSV exceeds bounded download size')
        rows = list(csv.DictReader(io.StringIO(payload.decode('utf-8-sig'))))
        def valid(row):
            if not (row.get('HomeTeam') and row.get('AwayTeam') and row.get('Time')
                    and row.get('FTHG', '').isdigit() and row.get('FTAG', '').isdigit()):
                return False
            if row.get('Div') and row['Div'] != code:
                return False
            return any(_valid_date(row.get('Date'), fmt) for fmt in ('%d/%m/%Y', '%d/%m/%y'))
        complete = [row for row in rows if valid(row)]
        if not complete:
            raise ValueError('No complete dated results in current-season CSV')
        if target.exists():
            with target.open(newline='', encoding='utf-8-sig') as handle:
                old_count = sum(1 for _ in csv.DictReader(handle))
            if len(complete) < old_count:
                raise ValueError('Refusing fewer current-season results than cached')
        # Preserve only complete, dated score records. Live fitting does not
        # use historical odds; do not let malformed price cells poison a fit.
        fields = ('Div', 'Date', 'Time', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG')
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix('.csv.tmp')
        with temp.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
            writer.writeheader(); writer.writerows(complete)
        temp.replace(target)
        provenance = {'source': url, 'retrieved_at': now, 'source_sha256': hashlib.sha256(payload).hexdigest(),
                      'rows': len(complete), 'transformation': 'complete_score_columns_only'}
        target.with_suffix('.source.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
        return {'status': 'updated', 'season': season, 'rows': len(complete)}
    except Exception as exc:
        return {'status': 'unavailable', 'season': season, 'reason': type(exc).__name__}


def _valid_date(value, fmt):
    try:
        datetime.strptime(value or '', fmt)
        return True
    except ValueError:
        return False
