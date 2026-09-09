# ============================================================================
# strength_rating.py — independent team-strength ratings (Dixon-Coles style)
# Replaces the old stub (which returned att=def=1.0 for every team).
#
# Method (documented assumptions):
#  - Poisson attack/defence model, Maher/Dixon-Coles basic form:
#      E[home goals] = att_h * def_a * league_avg * home_adv
#      E[away goals] = att_a * def_h * league_avg
#  - Time decay:  w = exp(-decay * days_ago), decay=0.003 (half-life ~231d).
#  - Scale semantics: league_avg ~= AWAY goals baseline (A), home_adv ~= H/A
#    ratio — NOT the overall mean. avg=(H+A)/2 is the wrong scale here
#    (symmetric 2-1 data needs avg=1.0, not 1.5). Intercepts are therefore
#    re-estimated inside the loop so predicted totals match observed totals
#    given the current ratings (E1: avg 1.152 ~= away avg 1.205).
#  - att/def fitted by alternating updates + geometric-mean normalisation
#    (identifiability), max 100 iters, tol 1e-6. Final clamp [0.6, 1.8] is
#    monotonic (preserves ordering); post-clamp re-fit keeps totals aligned.
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
RATING_VERSION = "poisson-intercept-v2"

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
# Negative cache with timestamps: transient failures (network, partial
# season) must not become permanent coverage loss for the process lifetime.
# Entries expire after RATINGS_TTL_S so a later retry can succeed once the
# dataset is available.
_no_coverage = {}


def _coverage_blocked(code, season):
    ts = _no_coverage.get((code, season))
    if ts is None:
        return False
    if time.time() - ts > RATINGS_TTL_S:
        _no_coverage.pop((code, season), None)
        _mem_cache.pop((code, season), None)
        return False
    return True


def _remember_no_coverage(code, season):
    _no_coverage[(code, season)] = time.time()


def clear_no_coverage():
    """Force retry of every failed league (operator/debug use)."""
    _no_coverage.clear()

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
        # Normalisation changes fitted intensity. Re-estimate the intercepts
        # so expected home/away goal sums match weighted observed goals.
        away_exposure = sum(w * teams[a]["att"] * teams[h]["def"] for w, h, a, _, _ in wrows)
        home_exposure = sum(w * teams[h]["att"] * teams[a]["def"] for w, h, a, _, _ in wrows)
        league_avg = max(1e-6, sum_a / max(away_exposure, 1e-9))
        home_adv = max(1e-6, sum_h / max(league_avg * home_exposure, 1e-9))
        if max_change < tol:
            break
    # clamp only the final output (monotonic — preserves ordering)
    for t in teams:
        teams[t]["att"] = round(min(1.8, max(0.6, teams[t]["att"])), 4)
        teams[t]["def"] = round(min(1.8, max(0.6, teams[t]["def"])), 4)
    away_exposure = sum(w * teams[a]["att"] * teams[h]["def"] for w, h, a, _, _ in wrows)
    home_exposure = sum(w * teams[h]["att"] * teams[a]["def"] for w, h, a, _, _ in wrows)
    league_avg = max(1e-6, sum_a / max(away_exposure, 1e-9))
    home_adv = max(1e-6, sum_h / max(league_avg * home_exposure, 1e-9))
    # Keep intercept precision: rounding a small positive intercept to zero
    # destroys its product with home_adv for low-scoring training samples.
    return teams, league_avg, home_adv


def fit_rho(rows, teams, league_avg, home_adv, lo=-0.20, hi=0.05, steps=25):
    """Grid-search Dixon-Coles rho maximising scoreline log-likelihood with
    fitted team strengths (documented approximation: strengths are held
    fixed from mle_rating, not re-fit jointly per rho). (lh,la,rho) pairs
    rejected by score-matrix validation are skipped. Returns (rho, n)."""
    from model import score_matrix
    scored = []
    for r in rows:
        try:
            x, y = int(r["fthg"]), int(r["ftag"])
        except (TypeError, ValueError):
            continue
        h, a = r.get("home"), r.get("away")
        if h not in teams or a not in teams:
            continue
        lh, la = strength_lam(teams[h]["att"], teams[a]["def"],
                              teams[a]["att"], teams[h]["def"],
                              league_avg, home_adv)
        if lh < 0.05 or la < 0.05:
            continue  # degenerate strengths — rho fit needs sane rates
        scored.append((min(x, 10), min(y, 10), round(lh, 3), round(la, 3)))
    if len(scored) < 20:
        return -0.13, len(scored)
    best = None
    for i in range(steps + 1):
        rho = round(lo + (hi - lo) * i / steps, 4)
        ll, cache, used = 0.0, {}, 0
        for x, y, lh, la in scored:
            key = (lh, la)
            m = cache.get(key)
            if m is None:
                try:
                    m, _ = score_matrix(lh, la, rho)
                except ValueError:
                    m = None
                cache[key] = m
            if m is None:
                continue
            ll += math.log(max(m.get((x, y), 1e-12), 1e-12))
            used += 1
        if used < 20:
            continue
        if best is None or ll > best[0]:
            best = (ll, rho)
    if best is None:
        return -0.13, 0
    return round(best[1], 3), len(scored)


def _ratings_path(league_code, season):
    return os.path.join(DATA_DIR, f"ratings_{league_code}_{season}.json")


def build_ratings(league_code, season, force=False):
    """Build (or reuse fresh) ratings file. Returns payload dict."""
    path = _ratings_path(league_code, season)
    if not force and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if payload.get("rating_version") == RATING_VERSION and time.time() - payload.get("built_at", 0) < RATINGS_TTL_S:
                _mem_cache[(league_code, season)] = payload
                return payload
        except Exception:
            pass
    csv_path = sh.download(league_code, season, out_dir=DATA_DIR)
    rows = [sh.normalize(r) for r in sh.load_rows(csv_path)]
    rows = [r for r in rows if r.get("fthg") is not None]
    teams, league_avg, home_adv = mle_rating(rows)
    rho, rho_n = fit_rho(rows, teams, league_avg, home_adv)
    payload = {
        "rating_version": RATING_VERSION,
        "league": league_code, "season": season,
        "league_avg": league_avg, "home_adv": home_adv,
        "rho": rho, "rho_n": rho_n,
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
        payload = _mem_cache[key]
        if payload.get("rating_version") == RATING_VERSION:
            return payload
    path = _ratings_path(league_code, season)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if payload.get("rating_version") != RATING_VERSION:
            return None
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


TEAM_ALIASES = {
    "man utd": "manchester united", "manchester utd": "manchester united",
    "man city": "manchester city", "manchester c": "manchester city",
    "spurs": "tottenham hotspur", "tottenham": "tottenham hotspur",
    "wolves": "wolverhampton wanderers", "wolverhampton": "wolverhampton wanderers",
    "west ham": "west ham united", "brighton": "brighton hove albion",
    "newcastle": "newcastle united", "leeds": "leeds united",
    "1 koln": "fc koln", "koln": "fc koln",
    "borussia monchengladbach": "m gladbach", "gladbach": "m gladbach",
    "paris saint germain": "paris sg", "psg": "paris sg",
    "inter": "internazionale milano", "inter milan": "internazionale milano",
    "milan": "ac milan", "roma": "as roma", "lazio": "ss lazio",
    "napoli": "ssc napoli", "verona": "hellas verona",
    "real sociedad": "sociedad", "athletic bilbao": "athletic club",
    "atletico madrid": "atletico madrid", "real betis": "betis",
    "bayer leverkusen": "leverkusen", "leipzig": "rb leipzig",
    "dortmund": "borussia dortmund", "bayern": "bayern munich",
    "n e c": "nijmegen", "nec": "nijmegen",
    "inverness ct": "inverness c",
    "inverness caledonian thistle": "inverness c",
}

# Club-type suffixes only. Team-CATEGORY markers (II, III, U19/U21/U23,
# B/C sides, reserves, women) must NEVER be stripped: senior, reserve and
# junior sides sharing a league label would otherwise cross-match.
_JUNK_SUFFIXES = (" fc", " cf", " sc", " afc", " ac", " us", " as", " rc")

# Tokens that force exact-only matching for that pair (senior vs reserve
# vs junior must not fuzzy-match each other).
CATEGORY_TOKENS = frozenset({
    "ii", "iii", "iv", "u17", "u18", "u19", "u20", "u21", "u23",
    "b", "c", "res", "reserves", "reserve", "youth", "women", "woman",
    "wfc", "ladies",
})

# Alias provenance: value -> "verified:<source>" or "heuristic".
# Verified = confirmed against football-data names; heuristic = best guess,
# safe only because matching stays inside one league file.
_ALIAS_SOURCE = {
    "man utd": "verified:football-data",
    "manchester utd": "verified:football-data",
    "man city": "verified:football-data",
    "manchester c": "verified:football-data",
    "spurs": "verified:football-data",
    "tottenham": "verified:football-data",
    "wolves": "verified:football-data",
    "wolverhampton": "verified:football-data",
    "west ham": "verified:football-data",
    "brighton": "verified:football-data",
    "newcastle": "verified:football-data",
    "leeds": "verified:football-data",
    "1 koln": "verified:football-data",
    "koln": "verified:football-data",
    "borussia monchengladbach": "verified:football-data",
    "gladbach": "verified:football-data",
    "paris saint germain": "verified:football-data",
    "psg": "verified:football-data",
    "inter": "heuristic",
    "inter milan": "heuristic",
    "milan": "heuristic",
    "roma": "heuristic",
    "lazio": "heuristic",
    "napoli": "heuristic",
    "verona": "heuristic",
    "real sociedad": "heuristic",
    "athletic bilbao": "heuristic",
    "atletico madrid": "heuristic",
    "real betis": "heuristic",
    "bayer leverkusen": "heuristic",
    "leipzig": "heuristic",
    "dortmund": "heuristic",
    "bayern": "heuristic",
    "n e c": "verified:ratings-file",
    "nec": "verified:ratings-file",
    "inverness ct": "verified:ratings-file",
    "inverness caledonian thistle": "verified:ratings-file",
}


def normalize_team_name(name):
    """Alias table + junk-suffix strip + lowercase alnum. League scoping is
    inherent: ratings files are per-league, so fuzzy matches never cross
    leagues (this bounds false-match risk, e.g. La Coruna vs Alaves)."""
    n = norm(name)
    n = TEAM_ALIASES.get(n, n)
    for junk in _JUNK_SUFFIXES:
        if n.endswith(junk):
            n = n[: -len(junk)].strip()
    return TEAM_ALIASES.get(n, n)


def match_team(name, teams):
    """Resolve a team name to a ratings key: exact norm, else difflib ratio
    >= 0.82, else token Jaccard >= 0.5, else substring, else None (caller
    rejects full coverage). Order matters: strict first, loose last.
    Pairs involving a team-CATEGORY token (II, U21, women, ...) match by
    exact normalized name only — fuzzy must never merge senior/reserve."""
    import difflib
    if not name or not teams:
        return None
    n = normalize_team_name(name)
    canon = {}
    for t in teams:
        canon.setdefault(normalize_team_name(t), t)
    if n in canon:
        return canon[n]

    def _category_locked(a, b):
        toks = set(a.split()) | set(b.split())
        return bool(toks & CATEGORY_TOKENS)

    best, best_r = None, 0.0
    for cn, t in canon.items():
        if _category_locked(n, cn):
            continue
        r = difflib.SequenceMatcher(None, n, cn).ratio()
        if r > best_r:
            best, best_r = t, r
    if best_r >= 0.82:
        return best
    toks = set(n.split())
    best, best_j = None, 0.0
    for cn, t in canon.items():
        if _category_locked(n, cn):
            continue
        ct = set(cn.split())
        union = toks | ct
        j = len(toks & ct) / len(union) if union else 0.0
        if j > best_j:
            best, best_j = t, j
    if best_j >= 0.5:
        return best
    for cn, t in canon.items():
        if _category_locked(n, cn):
            continue
        if n in cn or cn in n:
            return t
    return None


MISS_LOG_PATH = os.path.join(DATA_DIR, "team_match_misses.json")
MISS_LOG_CAP = 200


def log_match_miss(league_code, name):
    """Append unresolved provider team names (capped) so the alias table can
    be grown from real mismatch logs instead of guesses."""
    if not name:
        return
    try:
        try:
            with open(MISS_LOG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = []
        key = f"{league_code}|{norm(name)}"
        if any(d.get("key") == key for d in data):
            return
        data.append({"key": key, "league": league_code, "name": name,
                     "first_seen": time.time()})
        data = data[-MISS_LOG_CAP:]
        tmp = MISS_LOG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, MISS_LOG_PATH)
    except Exception:
        pass


def strength_lams(home, away, league_label, season=None):
    """Independent (non-market) lambdas. Returns (lh, la) or None if the
    league has no ratings coverage — caller must fall back to market λ."""
    code = resolve_code(league_label)
    if not code:
        return None
    season = season or resolve_season(code)
    if _coverage_blocked(code, season):
        return None
    payload = load_ratings(code, season)
    if not payload or not payload.get("teams"):
        # lazy build once (cached afterwards); remember failures
        try:
            payload = build_ratings(code, season)
        except Exception:
            _remember_no_coverage(code, season)
            return None
        if not payload.get("teams"):
            _remember_no_coverage(code, season)
            return None
    teams = payload["teams"]
    hk = match_team(home, teams)
    ak = match_team(away, teams)
    # An unmatched provider team name is not full model coverage.  Falling
    # back to a neutral team here used to masquerade as an independent signal.
    if not hk:
        log_match_miss(code, home)
    if not ak:
        log_match_miss(code, away)
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


def get_league_rho(league_label, season=None):
    """Per-league Dixon-Coles rho from the ratings file; RHO_DEFAULT when
    the league has no coverage (never raises, never blocks)."""
    from model import RHO_DEFAULT
    code = resolve_code(league_label)
    if not code:
        return RHO_DEFAULT
    season = season or resolve_season(code)
    if _coverage_blocked(code, season):
        return RHO_DEFAULT
    payload = load_ratings(code, season)
    if payload is None:
        try:
            payload = build_ratings(code, season)
        except Exception:
            _remember_no_coverage(code, season)
            return RHO_DEFAULT
    rho = (payload or {}).get("rho", None)
    try:
        return round(float(rho), 3)
    except (TypeError, ValueError):
        return RHO_DEFAULT


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
