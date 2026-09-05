# ============================================================================
# strength_rating.py — independent team-strength ratings (Dixon-Coles style)
# Replaces the old stub (which returned att=def=1.0 for every team).
#
# Method (documented assumptions):
#  - Poisson attack/defence model, Maher/Dixon-Coles basic form:
#      E[home goals] = att_h * def_a * league_avg * home_adv
#      E[away goals] = att_a * def_h * league_avg
#  - Time decay:  w = exp(-decay * days_ago), decay=0.003 (half-life ~231d).
#  - league_avg / home_adv estimated per (league, season) from weighted data.
#  - att/def fitted by alternating updates + geometric-mean normalisation
#    (identifiability: mean att = mean def = 1), max 100 iters, tol 1e-6.
#  - Unknown teams (promoted / name mismatch) fail full coverage explicitly;
#    they are never replaced by a neutral rating masquerading as evidence.
#  - Ratings cached to data/ratings_{CODE}_{SEASON}.json, rebuilt if older
#    than 7 days. Live path resolves season = current file with >=50 matches,
#    else previous season. Backtest callers MUST pass the previous season
#    explicitly (no lookahead).
# stdlib only.
# ============================================================================
import json
import math
import os
import re
import time
import unicodedata
from datetime import date, datetime

import scraper_historical as sh
from model import blend_lams, strength_lam

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
RATINGS_TTL_S = 7 * 24 * 3600
MIN_MATCHES_FOR_SEASON = 50

# 1xbit league label (normalised) -> football-data league code.
LEAGUE_MAP = {
    "england premier league": "E0",
    "england championship": "E1",
    "england league one": "E2",
    "england league two": "E3",
    "england national league": "EC",
    "spain la liga": "SP1",
    "spain segunda division": "SP2",
    "germany bundesliga": "D1",
    "germany bundesliga 2": "D2",
    "germany 2 bundesliga": "D2",
    "italy serie a": "I1",
    "italy serie b": "I2",
    "france ligue 1": "F1",
    "france ligue 2": "F2",
    "netherlands eredivisie": "N1",
    "portugal liga portugal": "P1",
    "portugal primeira liga": "P1",
    "belgium first division a": "B1",
    "belgium division 1": "B1",
    "turkey super lig": "T1",
    "turkey superliga": "T1",
    "greece superleague": "G1",
    "greece super league": "G1",
    "scotland premiership": "SC0",
    "scotland championship": "SC1",
    "scotland league one": "SC2",
    "scotland league two": "SC3",
}

_mem_cache = {}
_no_coverage = set()

KNOWN_CODES = {"E0", "E1", "E2", "E3", "EC", "SC0", "SC1", "SC2", "SC3",
               "D1", "D2", "SP1", "SP2", "I1", "I2", "F1", "F2",
               "N1", "B1", "P1", "T1", "G1"}


def resolve_code(label_or_code):
    """Accept a football-data code ('E0') or a 1xbit league label."""
    if not label_or_code:
        return None
    cand = str(label_or_code).strip().upper()
    if cand in KNOWN_CODES:
        return cand
    return league_code_for(label_or_code)


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = s.encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def parse_fd_date(s):
    """football-data uses DD/MM/YYYY; also accept ISO. Returns date or None."""
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def current_season_code(today=None):
    today = today or date.today()
    y = today.year if today.month >= 7 else today.year - 1
    return f"{y % 100:02d}{(y + 1) % 100:02d}"


def prev_season_code(season):
    a, b = int(season[:2]), int(season[2:])
    return f"{(a - 1) % 100:02d}{(b - 1) % 100:02d}"


def mle_rating(rows, time_decay_per_day=0.003, iterations=100, tol=1e-6):
    """rows: normalized dicts with home/away/fthg/ftag/date. Returns
    (teams {name: {att, def}}, league_avg, home_adv)."""
    usable = []
    for r in rows:
        d = parse_fd_date(r.get("date"))
        if d is None or r.get("fthg") is None or r.get("ftag") is None:
            continue
        if not r.get("home") or not r.get("away"):
            continue
        usable.append((d, r["home"], r["away"], float(r["fthg"]), float(r["ftag"])))
    if not usable:
        return {}, 1.35, 1.25
    latest = max(d for d, _, _, _, _ in usable)
    wrows = []
    for d, h, a, fthg, ftag in usable:
        w = math.exp(-time_decay_per_day * max(0, (latest - d).days))
        wrows.append((w, h, a, fthg, ftag))
    sw = sum(w for w, _, _, _, _ in wrows)
    league_avg = sum(w * (fthg + ftag) for w, _, _, fthg, ftag in wrows) / (2.0 * sw)
    sum_h = sum(w * fthg for w, _, _, fthg, _ in wrows)
    sum_a = sum(w * ftag for w, _, _, _, ftag in wrows)
    home_adv = (sum_h / sum_a) if sum_a > 0 else 1.25

    teams = {}
    for _, h, a, _, _ in wrows:
        for t in (h, a):
            if t not in teams:
                teams[t] = {"att": 1.0, "def": 1.0}

    for _ in range(iterations):
        max_change = 0.0
        # attack update (no clamp inside loop — clamp would fake a fixed point)
        num = {t: 0.0 for t in teams}
        den = {t: 0.0 for t in teams}
        for w, h, a, fthg, ftag in wrows:
            num[h] += w * fthg
            den[h] += w * league_avg * home_adv * teams[a]["def"]
            num[a] += w * ftag
            den[a] += w * league_avg * teams[h]["def"]
        for t in teams:
            new = max(1e-6, num[t] / den[t] if den[t] > 0 else 1.0)
            max_change = max(max_change, abs(new - teams[t]["att"]))
            teams[t]["att"] = new
        # defence update
        num = {t: 0.0 for t in teams}
        den = {t: 0.0 for t in teams}
        for w, h, a, fthg, ftag in wrows:
            num[a] += w * fthg
            den[a] += w * league_avg * home_adv * teams[h]["att"]
            num[h] += w * ftag
            den[h] += w * league_avg * teams[a]["att"]
        for t in teams:
            new = max(1e-6, num[t] / den[t] if den[t] > 0 else 1.0)
            max_change = max(max_change, abs(new - teams[t]["def"]))
            teams[t]["def"] = new
        # geometric-mean normalisation (identifiability)
        for key in ("att", "def"):
            g = math.exp(sum(math.log(max(1e-9, teams[t][key])) for t in teams) / len(teams))
            for t in teams:
                teams[t][key] /= g
        if max_change < tol:
            break
    # clamp only the final output (monotonic — preserves ordering)
    for t in teams:
        teams[t]["att"] = round(min(1.8, max(0.6, teams[t]["att"])), 4)
        teams[t]["def"] = round(min(1.8, max(0.6, teams[t]["def"])), 4)
    return teams, round(league_avg, 4), round(home_adv, 4)


def _ratings_path(league_code, season):
    return os.path.join(DATA_DIR, f"ratings_{league_code}_{season}.json")


def build_ratings(league_code, season, force=False):
    """Build (or reuse fresh) ratings file. Returns payload dict."""
    path = _ratings_path(league_code, season)
    if not force and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if time.time() - payload.get("built_at", 0) < RATINGS_TTL_S:
                _mem_cache[(league_code, season)] = payload
                return payload
        except Exception:
            pass
    csv_path = sh.download(league_code, season, out_dir=DATA_DIR)
    rows = [sh.normalize(r) for r in sh.load_rows(csv_path)]
    rows = [r for r in rows if r.get("fthg") is not None]
    teams, league_avg, home_adv = mle_rating(rows)
    payload = {
        "league": league_code, "season": season,
        "league_avg": league_avg, "home_adv": home_adv,
        "teams": teams, "n_matches": len(rows),
        "built_at": time.time(),
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.replace(tmp, path)
    _mem_cache[(league_code, season)] = payload
    return payload


def load_ratings(league_code, season):
    key = (league_code, season)
    if key in _mem_cache:
        return _mem_cache[key]
    path = _ratings_path(league_code, season)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        _mem_cache[key] = payload
        return payload
    except Exception:
        return None


def resolve_season(league_code):
    """Live path: current season file if >=50 matches else previous season."""
    cur = current_season_code()
    payload = load_ratings(league_code, cur)
    if payload and payload.get("n_matches", 0) >= MIN_MATCHES_FOR_SEASON:
        return cur
    return prev_season_code(cur)


def league_code_for(label):
    if not label:
        return None
    return LEAGUE_MAP.get(norm(label))


def match_team(name, teams):
    """Resolve a team name to a ratings key: exact norm, else token Jaccard
    >= 0.5, else None (caller rejects full coverage)."""
    if not name or not teams:
        return None
    aliases = {
        "1 koln": "fc koln",
        "borussia monchengladbach": "m gladbach",
        "paris saint germain": "paris sg",
    }
    n = aliases.get(norm(name), norm(name))
    for t in teams:
        if aliases.get(norm(t), norm(t)) == n:
            return t
    toks = set(n.split())
    best, best_j = None, 0.0
    for t in teams:
        ct = set(aliases.get(norm(t), norm(t)).split())
        union = toks | ct
        j = len(toks & ct) / len(union) if union else 0.0
        if j > best_j:
            best, best_j = t, j
    return best if best_j >= 0.5 else None


def strength_lams(home, away, league_label, season=None):
    """Independent (non-market) lambdas. Returns (lh, la) or None if the
    league has no ratings coverage — caller must fall back to market λ."""
    code = resolve_code(league_label)
    if not code:
        return None
    season = season or resolve_season(code)
    if (code, season) in _no_coverage:
        return None
    payload = load_ratings(code, season)
    if not payload or not payload.get("teams"):
        # lazy build once (cached afterwards); remember failures
        try:
            payload = build_ratings(code, season)
        except Exception:
            _no_coverage.add((code, season))
            return None
        if not payload.get("teams"):
            _no_coverage.add((code, season))
            return None
    teams = payload["teams"]
    hk = match_team(home, teams)
    ak = match_team(away, teams)
    # An unmatched provider team name is not full model coverage.  Falling
    # back to a neutral team here used to masquerade as an independent signal.
    if not hk or not ak:
        return None
    hatt = teams[hk]["att"]
    adef = teams[ak]["def"]
    aatt = teams[ak]["att"]
    hdef = teams[hk]["def"]
    lh, la = strength_lam(hatt, adef, aatt, hdef,
                          payload.get("league_avg", 1.35),
                          payload.get("home_adv", 1.25))
    lh = min(4.0, max(0.3, lh))
    la = min(4.0, max(0.3, la))
    return round(lh, 3), round(la, 3)


def hybrid_lams(home, away, league_label, market_lh, market_la,
                weight=0.4, season=None):
    """Blend market λ with independent strength λ.
    weight = strength share (0.4 default, config strength_weight).
    Returns (lh, la, source) where source is 'market+strength' or
    'market-only' (no coverage — unbiased fallback, never forced)."""
    s = strength_lams(home, away, league_label, season=season)
    if s is None:
        return market_lh, market_la, "market-only"
    lh = blend_lams(market_lh, s[0], 1.0 - weight)
    la = blend_lams(market_la, s[1], 1.0 - weight)
    return round(lh, 3), round(la, 3), "market+strength"


def compute_rating(league="E0", season="2425"):
    """Legacy entry point kept for compat — now builds real ratings."""
    payload = build_ratings(league, season, force=True)
    return {"teams": payload["teams"], "league_avg": payload["league_avg"],
            "home_adv": payload["home_adv"], "season": season, "league": league}


if __name__ == "__main__":
    import sys
    code = sys.argv[1] if len(sys.argv) > 1 else "E0"
    season = sys.argv[2] if len(sys.argv) > 2 else prev_season_code(current_season_code())
    p = build_ratings(code, season, force=True)
    print(f"{code} {season}: {p['n_matches']} matches, avg={p['league_avg']}, home_adv={p['home_adv']}, teams={len(p['teams'])}")
