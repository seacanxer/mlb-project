import gzip
import io
import json
import time
import urllib.request

BASE = "https://1xbit.com/service-api/LineFeed/"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        data = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
        return json.loads(data)


def list_matches(sport=1, count=50, mode=1, country=169):
    url = f"{BASE}BestGamesExtZip?sports={sport}&count={count}&lng=en&mode={mode}&country={country}"
    j = fetch(url)
    return [v for v in j.get("Value", []) if v.get("I")]


def list_matches_paginated(sport=1, count=500, mode=1, country=169, window_hours=16, max_pages=60):
    now = time.time()
    seen, order = {}, []
    for page in range(max_pages):
        url = f"{BASE}BestGamesExtZip?sports={sport}&count={count}&lng=en&mode={mode}&country={country}&page={page}"
        j = fetch(url)
        if not isinstance(j, dict) or not isinstance(j.get("Value"), list):
            raise ValueError("Invalid fixture feed response")
        v = [x for x in j["Value"] if isinstance(x, dict) and x.get("I")]
        if not v:
            break
        new = False
        for x in v:
            if x["I"] in seen:
                continue
            s = x.get("S")
            if not s:
                continue
            if not (now - 60 <= s <= now + float(window_hours) * 3600):
                continue
            seen[x["I"]] = x
            order.append(x)
            new = True
        if page > 0 and not new:
            break
    return order


def get_match(mid, country=169):
    url = f"{BASE}GetGameZip?id={mid}&lng=en&country={country}"
    j = fetch(url)
    return j.get("Value", {})


# Sub-game type IDs seen in GetGameZip?SG (GroupEvents=true):
#   TI=2  -> Corners (full-time OU/AH mirror the goal-market G/T codes)
#   TI=8  -> Yellow Cards (count OU)
#   TI=10 -> Cards / booking points (points OU, yellow=1 + red=2 per house rules)
# Verified 2026-10-03 against a live Nations League fixture: corner OU lines
# 6.5-10.5 sit in G=17/G=99, handicap in G=2 — same T codes as goals.
SECONDARY_TI = {'corners': 2, 'yellow_cards': 8, 'cards': 10}

# Contract keys added for secondary markets. Main extract_markets() always
# carries them (empty by default) so downstream code never KeyErrors;
# population is opt-in via extract_secondary_markets() to avoid 3-4x API
# calls on every scan.
SECONDARY_KEYS = ('odds_corners_ou', 'odds_corner_ah',
                  'odds_yellow_ou', 'odds_cards_ou')


def get_match_grouped(mid, country=169):
    """GetGameZip with sub-game grouping so SG/GE are populated."""
    url = (f"{BASE}GetGameZip?id={mid}&lng=en&country={country}"
           "&cfview=0&isSubGames=true&GroupEvents=true&countevents=500")
    j = fetch(url)
    return j.get("Value", {}) if isinstance(j, dict) else {}


def get_subgame_ids(mid, country=169):
    """Return {'corners': id, 'yellow_cards': id, 'cards': id} for FT only.

    FT = no period (P absent) and empty PN. Half sub-games (P=1/2) are
    ignored: the secondary model is full-time only. Never raises — a
    missing/renamed sub-game yields a missing key, not a crash.
    """
    try:
        v = get_match_grouped(mid, country=country)
    except Exception:
        return {}
    out = {}
    for sg in v.get("SG", []) or []:
        try:
            if sg.get("P") is not None or (sg.get("PN") or "") != "":
                continue
            ti = sg.get("TI")
            sid = sg.get("I")
            if sid is None:
                continue
            for name, want in SECONDARY_TI.items():
                if ti == want and name not in out:
                    out[name] = sid
        except (AttributeError, TypeError):
            continue
    return out


def _parse_ou_ah(entries):
    """Shared goal/corner/card OU+AH parser over flat or grouped entries."""
    odds_ou, odds_ah = {}, {"home": [], "away": []}
    stack = list(entries)
    while stack:
        e = stack.pop()
        if isinstance(e, list):
            stack.extend(e)
            continue
        if not isinstance(e, dict):
            continue
        t, c, g, p = e.get("T"), e.get("C"), e.get("G"), e.get("P")
        if ((g == 17 and t in (9, 10)) or
                (g == 99 and t in (3827, 3828))) and p is not None:
            try:
                price = float(c)
            except (TypeError, ValueError):
                continue
            if not (price > 1):
                continue
            side = 9 if t in (9, 3827) else 10
            try:
                line = float(p)
            except (TypeError, ValueError):
                continue
            odds_ou.setdefault(line, {})[side] = price
        elif ((g == 2 and t == 7) or (g == 2854 and t == 3829)) and p is not None:
            try:
                odds_ah["home"].append((float(p), float(c)))
            except (TypeError, ValueError):
                continue
        elif ((g == 2 and t == 8) or (g == 2854 and t == 3830)) and p is not None:
            try:
                odds_ah["away"].append((float(p), float(c)))
            except (TypeError, ValueError):
                continue
    for side in ("home", "away"):
        odds_ah[side] = sorted(odds_ah[side])
    if not odds_ah["home"] and not odds_ah["away"]:
        odds_ah = {}
    return odds_ou, odds_ah


def get_subgame_markets(sub_id, country=169):
    """Fetch one FT sub-game and return {'odds_ou': {...}, 'odds_ah': {...}}."""
    v = get_match_grouped(sub_id, country=country)
    groups = v.get("GE") or []
    entries = []
    for g in groups:
        entries.extend(g.get("E", []) or [])
    if not entries and v.get("E"):
        entries = v.get("E")
    odds_ou, odds_ah = _parse_ou_ah(entries)
    return {"odds_ou": odds_ou, "odds_ah": odds_ah}


def extract_secondary_markets(mid, country=169):
    """Opt-in secondary fetch. Returns SECONDARY_KEYS + subgame_ids.

    Never raises: every failure degrades to an empty book for that market,
    which the engine must treat as unavailable (state C), never as a price.
    """
    out = {key: {} for key in SECONDARY_KEYS}
    out["secondary_subgame_ids"] = {}
    try:
        ids = get_subgame_ids(mid, country=country)
    except Exception:
        return out
    out["secondary_subgame_ids"] = dict(ids)
    mapping = (("corners", "odds_corners_ou", "odds_corner_ah"),
               ("yellow_cards", "odds_yellow_ou", None),
               ("cards", "odds_cards_ou", None))
    for name, ou_key, ah_key in mapping:
        sid = ids.get(name)
        if sid is None:
            continue
        try:
            mk = get_subgame_markets(sid, country=country)
        except Exception:
            continue
        if mk.get("odds_ou"):
            out[ou_key] = mk["odds_ou"]
        if ah_key and mk.get("odds_ah"):
            out[ah_key] = mk["odds_ah"]
    return out


def extract_markets(v):
    odds = v.get("E", []) or []
    out = {
        "match_id": v.get("I"),
        "home": v.get("O1"),
        "away": v.get("O2"),
        "start_ts": v.get("S"),
        "league": v.get("L"),
        "wp": v.get("WP"),
        "odds_1x2": {},
        "odds_ou": {},
        "odds_ah": {},
        "odds_btts": {},
        # Secondary books live in FT sub-games (see SECONDARY_TI). Populated
        # only by extract_secondary_markets(); empty here means unavailable.
        "odds_corners_ou": {},
        "odds_corner_ah": {},
        "odds_yellow_ou": {},
        "odds_cards_ou": {},
    }
    for e in odds:
        t, c, g, p = e.get("T"), e.get("C"), e.get("G"), e.get("P")
        if g == 1 and t in (1, 2, 3):
            out["odds_1x2"][t] = c
        # 1xbit exposes whole/half and split-quarter lines in separate groups.
        # Normalize both groups into the same contract shape used by the engine.
        elif ((g == 17 and t in (9, 10)) or
              (g == 99 and t in (3827, 3828))) and p is not None:
            side = 9 if t in (9, 3827) else 10
            out["odds_ou"].setdefault(p, {})[side] = c
        elif ((g == 2 and t == 7) or (g == 2854 and t == 3829)) and p is not None:
            out["odds_ah"].setdefault("home", []).append((p, c))
        elif ((g == 2 and t == 8) or (g == 2854 and t == 3830)) and p is not None:
            out["odds_ah"].setdefault("away", []).append((p, c))
        elif g == 19 and t in (180, 181):
            # Both teams to score: 180=Yes, 181=No.
            out["odds_btts"]["yes" if t == 180 else "no"] = c
    return out


def scrape_all(delay=0.2, to_json="odds_live.json"):
    rows = []
    matches = list_matches()
    for m in matches:
        try:
            v = get_match(m["I"])
            rows.append(extract_markets(v))
            time.sleep(delay)
        except Exception as e:
            rows.append({"match_id": m.get("I"), "error": str(e)})
    if to_json:
        with open(to_json, "w") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
    return rows


if __name__ == "__main__":
    out = scrape_all()
    print(f"scraped {len(out)} matches")
    for o in out[:5]:
        print(o.get("league"), "|", o.get("home"), "vs", o.get("away"), "| 1X2:", o.get("odds_1x2"), "| OU2.5:", o.get("odds_ou", {}).get(2.5), "| AH:", o.get("odds_ah"))
