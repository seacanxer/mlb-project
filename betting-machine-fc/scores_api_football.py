import urllib.request
import json
import time
import re
import unicodedata
import difflib
from datetime import date, timedelta

API_KEY = "a1fd36c21c25a563001e5d547629f0ee"
BASE_URL = "https://v3.football.api-sports.io"
UA = {"User-Agent": "Mozilla/5.0"}
_CACHE = {"ts": 0.0, "index": None, "ttl": 600}

def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = s.encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    s = re.sub(r"\s+", " ", s).strip()
    return s

def fetch_fixtures(date_str):
    url = f"{BASE_URL}/fixtures?date={date_str}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "x-rapidapi-key": API_KEY,
        "x-rapidapi-host": "v3.football.api-sports.io"
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if data.get("errors"):
                print(f"[api-football] Error for {date_str}: {data['errors']}")
                return []
            return data.get("response", [])
    except Exception as e:
        print(f"[api-football] fetch failed for {date_str}: {e}")
        return []

def fetch_recent_results(days=3, use_cache=True):
    now = time.time()
    if use_cache and _CACHE["index"] is not None and now - _CACHE["ts"] < _CACHE["ttl"]:
        return _CACHE["index"]

    index = {}
    today = date.today()
    for d in range(0, -days, -1):
        dt = today + timedelta(days=d)
        date_str = dt.isoformat()
        fixtures = fetch_fixtures(date_str)
        if not fixtures:
            continue
        for f in fixtures:
            teams = f.get("teams", {})
            home = teams.get("home", {}).get("name")
            away = teams.get("away", {}).get("name")
            goals = f.get("goals", {})
            home_goals = goals.get("home")
            away_goals = goals.get("away")
            if home is None or away is None or home_goals is None or away_goals is None:
                continue
            status = f.get("fixture", {}).get("status", {}).get("short")
            if status not in ("FT", "AET", "PEN", "FINISHED"):
                continue
            key = (norm(home), norm(away))
            row = {
                "home": home,
                "away": away,
                "home_goals": home_goals,
                "away_goals": away_goals,
                "date_key": date_str,
                "fixture_id": f.get("fixture", {}).get("id")
            }
            if key not in index:
                index[key] = []
            index[key].append(row)
        time.sleep(0.2)
    _CACHE["ts"] = time.time()
    _CACHE["index"] = index
    return index

def build_lookup(index):
    lookup = {}
    for (hn, an), rows in index.items():
        for row in rows:
            lookup.setdefault((hn, an), []).append(row)
    return lookup

def _fuzzy_find(home, away, lookup, target_date=None):
    best = None
    best_score = 0.0
    best_date_match = None
    best_date_score = 0.0
    htoks = set(t for t in norm(home).split() if len(t) > 1)
    atoks = set(t for t in norm(away).split() if len(t) > 1)
    full_h = norm(home)
    full_a = norm(away)
    for (ch, ca), rows in lookup.items():
        for row in rows:
            chtoks = set(ch.split())
            catoks = set(ca.split())
            if htoks or chtoks:
                inter_h = len(htoks & chtoks)
                union_h = len(htoks | chtoks)
                jacc_h = inter_h / union_h if union_h else 0.0
            else:
                jacc_h = 0.0
            if atoks or catoks:
                inter_a = len(atoks & catoks)
                union_a = len(atoks | catoks)
                jacc_a = inter_a / union_a if union_a else 0.0
            else:
                jacc_a = 0.0
            seq_h = difflib.SequenceMatcher(None, full_h, ch).ratio()
            seq_a = difflib.SequenceMatcher(None, full_a, ca).ratio()
            score = (jacc_h + jacc_a + seq_h + seq_a) / 4.0
            if target_date and row.get('date_key') == target_date.isoformat():
                if score > best_date_score:
                    best_date_score = score
                    best_date_match = row
            else:
                if score > best_score:
                    best_score = score
                    best = row
    if target_date:
        if best_date_match and best_date_score >= 0.9:
            return best_date_match
        return None
    else:
        if best and best_score >= 0.5:
            return best
        if best and best_score >= 0.3:
            return best
        return None

def find_result(home, away, lookup, kickoff_date=None):
    hn = norm(home)
    an = norm(away)
    cands = lookup.get((hn, an)) or []
    if cands:
        if kickoff_date:
            for row in cands:
                if row.get('date_key') == kickoff_date.isoformat():
                    return row
            # Never fall back to a different-date result: that fabricates scores
            # from a different fixture that happens to share team names.
            return None
        return cands[0]
    # fuzzy fallback
    return _fuzzy_find(home, away, lookup, target_date=kickoff_date)