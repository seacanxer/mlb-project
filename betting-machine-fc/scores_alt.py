"""Alternative results feeds: TheSportsDB + OpenLigaDB.

Fallback sources used after FlashScore (primary) fails to match a bet.
Coverage is limited to major leagues, but both are free and require no API key.

Architecture mirrors scores_flashscore.py:
  fetch_recent_results() -> index dict
  build_lookup(index)     -> lookup dict keyed by (norm(home), norm(away))
  find_result(home, away, lookup, kickoff_date) -> row or None
"""
import json
import re
import time
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

UA = {"User-Agent": "Mozilla/5.0"}

_CACHE = {"ts": 0.0, "index": None, "ttl": 600}

# TheSportsDB league IDs for major soccer leagues.
_THESPORTSDB_LEAGUES = [
    "4327",  # English Premier League
    "4335",  # Spanish La Liga
    "4331",  # German Bundesliga
    "4334",  # Italian Serie A
    "4332",  # French Ligue 1
    "4346",  # MLS
    "4358",  # Brazilian Serie A
    "4330",  # Scottish Premiership
    "4344",  # Portuguese Primeira Liga
    "4356",  # Australian A-League
    "4337",  # Dutch Eredivisie
    "4338",  # Belgian Pro League
    "4480",  # English League Championship (alt)
    "4400",  # English League One
    "4488",  # English League Two
    "4624",  # Norwegian Eliteserien
]

# OpenLigaDB league shortcuts (German-focused but reliable, no API key).
_OPENLIGADB_LEAGUES = ["bl1", "bl2", "bl3", "dfb"]


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = s.encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    # Normalize women's-team suffixes (same logic as scores_flashscore.norm)
    s = re.sub(r"\s*\(?wom[ae]n\)?\s*", " w ", s)
    s = re.sub(r"\s+\(?w\)?\s*$", " w ", s)
    s = s.replace("altay", "altai")
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ---------------------------------------------------------------------------
# TheSportsDB
# ---------------------------------------------------------------------------
def _fetch_thesportsdb():
    """Fetch recent finished events from TheSportsDB eventspastleague endpoint.

    Free tier returns ~15 most recent past events per league, which is enough
    for a fallback that only runs on bets FlashScore could not match.
    """
    index = {}

    def fetch_league(lid):
        url = f"https://www.thesportsdb.com/api/v1/json/3/eventspastleague.php?id={lid}"
        last_error = None
        for attempt in range(2):
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=10) as r:
                    return lid, json.loads(r.read().decode()), None
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(.2)
        return lid, None, last_error

    payloads = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch_league, lid) for lid in _THESPORTSDB_LEAGUES]
        for future in as_completed(futures):
            payloads.append(future.result())
    for lid, data, error in payloads:
        if data is None:
            print(f"[scores_alt] WARN thesportsdb league {lid}: {error}", flush=True)
            continue
        events = data.get("events") or []
        for e in events:
            home = e.get("strHomeTeam") or ""
            away = e.get("strAwayTeam") or ""
            hg = e.get("intHomeScore")
            ag = e.get("intAwayScore")
            if hg is None or ag is None:
                continue
            status = (e.get("strStatus") or "").upper()
            if status not in ("FT", "MATCH FINISHED", "FIN"):
                continue
            key = (norm(home), norm(away))
            row = {
                "home": home,
                "away": away,
                "home_goals": int(hg),
                "away_goals": int(ag),
                "date_key": e.get("dateEvent") or "",
                "league": e.get("strLeague") or "",
                "source": "thesportsdb",
                "status": "ft",
                "period": "90min",
            }
            index.setdefault(key, []).append(row)
    return index


# ---------------------------------------------------------------------------
# OpenLigaDB
# ---------------------------------------------------------------------------
def _fetch_openligadb():
    """Fetch recent finished matchdays from OpenLigaDB (German leagues)."""
    index = {}

    def fetch_league(league):
        url = f"https://api.openligadb.de/getmatchdata/{league}"
        last_error = None
        for attempt in range(2):
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=10) as r:
                    return league, json.loads(r.read().decode()), None
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(.2)
        return league, None, last_error

    payloads = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(fetch_league, league) for league in _OPENLIGADB_LEAGUES]
        for future in as_completed(futures):
            payloads.append(future.result())
    for league, data, error in payloads:
        if data is None:
            print(f"[scores_alt] WARN openligadb {league}: {error}", flush=True)
            continue
        for m in data:
            if not m.get("matchIsFinished"):
                continue
            home = (m.get("team1") or {}).get("teamName") or ""
            away = (m.get("team2") or {}).get("teamName") or ""
            results = m.get("matchResults") or []
            final = None
            for r in results:
                if (r.get("resultName") or "").lower() in ("endstand", "endergebnis", "matchend"):
                    final = r
                    break
            if final is None and results:
                final = results[-1]  # last entry is usually the final
            if not final:
                continue
            hg = final.get("pointsTeam1")
            ag = final.get("pointsTeam2")
            if hg is None or ag is None:
                continue
            dstr = (m.get("matchDateTime") or "")[:10]
            key = (norm(home), norm(away))
            row = {
                "home": home,
                "away": away,
                "home_goals": int(hg),
                "away_goals": int(ag),
                "date_key": dstr,
                "league": league.upper(),
                "source": "openligadb",
            }
            index.setdefault(key, []).append(row)
    return index


# ---------------------------------------------------------------------------
# Unified interface
# ---------------------------------------------------------------------------
def fetch_recent_results(days=3, use_cache=True):
    """Fetch results from TheSportsDB + OpenLigaDB and merge into one index."""
    now = time.time()
    if use_cache and _CACHE["index"] is not None and now - _CACHE["ts"] < _CACHE["ttl"]:
        return _CACHE["index"]
    index = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        ts_future = pool.submit(_fetch_thesportsdb)
        oldb_future = pool.submit(_fetch_openligadb)
        for name, future in (('thesportsdb', ts_future), ('openligadb', oldb_future)):
            try:
                provider = future.result()
                for key, rows in provider.items():
                    index.setdefault(key, []).extend(rows)
            except Exception as exc:
                print(f"[scores_alt] WARN {name} fetch failed: {exc}", flush=True)
    _CACHE["ts"] = time.time()
    _CACHE["index"] = index
    return index


def build_lookup(index):
    lookup = {}
    for (hn, an), rows in index.items():
        for row in rows:
            lookup.setdefault((hn, an), []).append(row)
    return lookup


def find_result(home, away, lookup, kickoff_date=None):
    """Find a result. STRICT matching only — no fuzzy fallback.

    Returns the row matching the kickoff date (±1 day window). If no
    date-proximate row exists among exact-name candidates, returns None.
    """
    # Use the same complete-name alias policy as the primary feed.
    import scores_flashscore
    from football_formula_engine.fixture_matching import unique_result
    candidates = [row for h in scores_flashscore.name_keys(home)
                  for a in scores_flashscore.name_keys(away)
                  for row in lookup.get((h, a), [])]
    return unique_result(candidates, kickoff_date)
