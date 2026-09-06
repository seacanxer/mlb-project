import argparse
import asyncio
import json
import os
import re
import sys
import time
import unicodedata

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import httpx

from scraper_flashscore import fetch_feed, UA

CACHE_PATH = os.path.join(BASE_DIR, "crosscheck_cache.json")
MAIN_FEED_URL = "https://global.flashscore.ninja/2/x/feed/f_1_0_8_en_1"
ODDS_GQL = "https://global.ds.lsapp.eu/odds/pq_graphql?_hash=oce&eventId={mid}&projectId=2&geoIpCode=SG&geoIpSubdivisionCode=SG"
GQL_HEADERS = {
    "User-Agent": UA,
    "Referer": "https://www.flashscore.com/",
    "Accept": "*/*",
    "Origin": "https://www.flashscore.com",
}
AVG_BOOKMAKER = 997


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = s.encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_main_feed(body):
    rows = []
    cur_league = None
    for block in (body or "").split("\u00ac~"):
        block = block.lstrip("\u00ac")
        if not block:
            continue
        kv = {}
        for p in block.split("\u00ac"):
            if not p:
                continue
            pair = p.split("\u00f7")
            if len(pair) == 2:
                kv[pair[0]] = pair[1]
        if kv.get("ZA"):
            cur_league = kv["ZA"]
        if kv.get("AA"):
            rows.append({
                "id": kv["AA"],
                "home": kv.get("AE") or kv.get("FH") or "",
                "away": kv.get("AF") or kv.get("FK") or "",
                "home_pid": kv.get("JA") or "",
                "away_pid": kv.get("JB") or "",
                "league": cur_league or "",
                "kickoff": kv.get("AD") or "",
            })
    return rows


_MATCHES_CACHE = {"ts": 0.0, "rows": None}


def fetch_fs_matches():
    now = time.time()
    if _MATCHES_CACHE["rows"] is not None and now - _MATCHES_CACHE["ts"] < 300:
        return _MATCHES_CACHE["rows"]
    body = asyncio.run(fetch_feed(MAIN_FEED_URL))
    if not body:
        return []
    rows = parse_main_feed(body)
    _MATCHES_CACHE["ts"] = now
    _MATCHES_CACHE["rows"] = rows
    return rows


def find_fs_match(home, away, league=None, kickoff_ts=None, matches=None):
    if matches is None:
        matches = fetch_fs_matches()
    hn, an = norm(home), norm(away)
    best = None
    for m in matches:
        if norm(m["home"]) == hn and norm(m["away"]) == an:
            score = 80
            if league and league.lower() in (m["league"] or "").lower():
                score += 15
            if kickoff_ts:
                try:
                    if abs(int(m["kickoff"]) - int(kickoff_ts)) < 3600 * 6:
                        score += 15
                except (TypeError, ValueError):
                    pass
            if best is None or score > best[0]:
                best = (score, m)
    return best[1] if best else None


def fetch_odds_gql(match_id):
    r = httpx.get(ODDS_GQL.format(mid=match_id), headers=GQL_HEADERS, timeout=25, follow_redirects=True)
    r.raise_for_status()
    data = r.json()
    return data["data"]["findOddsByEventId"]


def market_from_payload(payload, bm, mtype, scope="FULL_TIME"):
    for t in payload.get("odds") or []:
        if t.get("bookmakerId") == bm and t.get("bettingType") == mtype and t.get("bettingScope") == scope:
            return t
    return None


def fs_ou_2_5(table):
    out = {"over": None, "under": None}
    for o in table.get("odds") or []:
        h = o.get("handicap") or {}
        line = h.get("value")
        sel = o.get("selection")
        if line is None or sel not in ("OVER", "UNDER"):
            continue
        try:
            line = float(line)
        except (TypeError, ValueError):
            continue
        if abs(line - 2.5) < 0.01:
            out[sel.lower()] = o.get("value")
    return out


def fs_ah_home(table, xbit_home_line=None, home_pid=None):
    rows_by_line = {}
    for o in table.get("odds") or []:
        h = o.get("handicap") or {}
        line = h.get("value")
        if line is None:
            continue
        try:
            line = float(line)
        except (TypeError, ValueError):
            continue
        rows_by_line.setdefault(line, []).append(o)
    pairs = []
    for line, rows in rows_by_line.items():
        if len(rows) < 2:
            continue
        away = home = None
        for o in rows:
            pid = o.get("eventParticipantId")
            if home_pid and pid == home_pid:
                home = o
            elif home_pid and pid and pid != home_pid:
                away = o
            else:
                if line < 0 and home is None:
                    home = o
                elif line >= 0 and away is None:
                    away = o
                elif home is None:
                    home = o
                elif away is None:
                    away = o
        if home and away:
            pairs.append((line, home.get("value"), away.get("value")))
    chosen = None
    if xbit_home_line is not None:
        try:
            target = float(xbit_home_line)
            chosen = min(pairs, key=lambda p: abs(p[0] - target))
        except (TypeError, ValueError):
            chosen = pairs[0] if pairs else None
    else:
        chosen = pairs[0] if pairs else None
    if chosen:
        return {"line": chosen[0], "home": chosen[1], "away": chosen[2]}
    return None


def crosscheck_match(home, away, league=None, kickoff_ts=None, matches=None):
    t0 = time.time()
    result = {
        "home": home,
        "away": away,
        "league": league,
        "fs_found": False,
        "fs_1x2": None,
        "fs_ou": None,
        "fs_ah": None,
        "note": "",
    }
    if matches is None:
        try:
            matches = fetch_fs_matches()
        except Exception as e:
            result["note"] = "fs feed error: %s" % e
            return result
    m = find_fs_match(home, away, league, kickoff_ts, matches)
    if not m:
        result["note"] = "no fs match found"
        return result
    result["fs_found"] = True
    result["fs_match_id"] = m["id"]
    result["fs_league"] = m["league"]
    try:
        payload = fetch_odds_gql(m["id"])
    except Exception as e:
        result["note"] = "odds gql error: %s" % e
        return result
    t1x2 = market_from_payload(payload, AVG_BOOKMAKER, "HOME_DRAW_AWAY")
    t_ou = market_from_payload(payload, AVG_BOOKMAKER, "OVER_UNDER")
    t_ah = market_from_payload(payload, AVG_BOOKMAKER, "ASIAN_HANDICAP")
    if t1x2:
        odds = {}
        for o in t1x2.get("odds") or []:
            if o.get("value") is None:
                continue
            if o.get("eventParticipantId") is None:
                odds["draw"] = o.get("value")
            elif m.get("home_pid") and o.get("eventParticipantId") == m["home_pid"]:
                odds["home"] = o.get("value")
            elif m.get("away_pid") and o.get("eventParticipantId") == m["away_pid"]:
                odds["away"] = o.get("value")
        if not odds.get("home") and not odds.get("away"):
            vals = [o.get("value") for o in (t1x2.get("odds") or []) if o.get("value")]
            if len(vals) >= 3:
                odds = {"home": vals[0], "draw": vals[1], "away": vals[2]}
        result["fs_1x2"] = odds or None
    if t_ou:
        ou = fs_ou_2_5(t_ou)
        if ou.get("over") or ou.get("under"):
            result["fs_ou"] = {"line": 2.5, **ou}
    if t_ah:
        xbit_line = None
        if kickoff_ts is None:
            xbit_line = None
        ah = fs_ah_home(t_ah, home_pid=m.get("home_pid"))
        if ah:
            result["fs_ah"] = ah
    result["_elapsed"] = round(time.time() - t0, 1)
    return result


def xbit_ou_over(item):
    main_ou = item.get("main_ou") or {}
    try:
        return float(main_ou.get("over_odds"))
    except (TypeError, ValueError):
        return None


def xbit_ah_home(item):
    main_ah = item.get("main_ah") or {}
    try:
        return float(main_ah.get("home_odds"))
    except (TypeError, ValueError):
        return None


def verdict_for(fs_ou_over, xbit_over, fs_ah_home_odds, xbit_ah_odds):
    def to_f(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def agree(a, b):
        a, b = to_f(a), to_f(b)
        if a is None or b is None:
            return None
        if a >= 1.7 and b >= 1.7:
            return True
        if a > 0 and b > 0:
            return abs(a - b) / min(a, b) <= 0.15
        return False

    v = agree(fs_ou_over, xbit_over)
    if v is not None:
        return "agree" if v else "disagree"
    v = agree(fs_ah_home_odds, xbit_ah_odds)
    if v is not None:
        return "agree" if v else "disagree"
    return "no_fs"


def _f(v):
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def crosscheck_board(board_path=None, limit=30):
    if board_path is None:
        board_path = os.path.join(BASE_DIR, "intel_board.json")
    with open(board_path, "r", encoding="utf-8") as f:
        board = json.load(f)
    items = board.get("board", [])
    watch = [x for x in items if x.get("decision") == "WATCH"]
    rest = [x for x in items if x.get("decision") != "WATCH"]
    rest.sort(key=lambda x: (x.get("coverage") != "full", x.get("start_ts") or 0))
    selected = (watch + rest[: max(0, limit - len(watch))])[:limit]
    rows = []
    cache = load_cache()
    matches = None
    fs_err = None
    try:
        matches = fetch_fs_matches()
    except Exception as e:
        fs_err = "fs feed error: %s" % e
    for item in selected:
        key = json.dumps((item.get("home") or "", item.get("away") or "", item.get("league") or ""), sort_keys=True)
        hit = cache.get(key)
        if hit:
            cc = hit
        else:
            if fs_err:
                cc = {"home": item.get("home"), "away": item.get("away"), "league": item.get("league"),
                      "fs_found": False, "fs_1x2": None, "fs_ou": None, "fs_ah": None, "note": fs_err}
            else:
                cc = crosscheck_match(item.get("home"), item.get("away"), item.get("league"),
                                     item.get("start_ts"), matches=matches)
            cache[key] = cc
        xbit_over = xbit_ou_over(item)
        xbit_ah = xbit_ah_home(item)
        fs_ou = cc.get("fs_ou") or {}
        fs_ah = cc.get("fs_ah") or {}
        fs_ou_over = fs_ou.get("over")
        fs_ah_home_odds = fs_ah.get("home") if fs_ah else None
        if cc.get("fs_found") and (fs_ou_over is not None or fs_ah_home_odds is not None):
            verdict = verdict_for(fs_ou_over, xbit_over, fs_ah_home_odds, xbit_ah)
        else:
            verdict = "no_fs"
        rows.append({
            "match": "%s vs %s" % (item.get("home"), item.get("away")),
            "home": item.get("home"),
            "away": item.get("away"),
            "league": item.get("league"),
            "fs_found": cc.get("fs_found"),
            "fs_ou_line": fs_ou.get("line") if fs_ou else None,
            "fs_ou_over_odds": _f(fs_ou_over),
            "xbit_ou_line": (item.get("main_ou") or {}).get("line"),
            "xbit_ou_over_odds": _f(xbit_over),
            "fs_ah_home": _f(fs_ah_home_odds),
            "fs_ah_line": fs_ah.get("line") if fs_ah else None,
            "xbit_ah_line": (item.get("main_ah") or {}).get("home_line"),
            "xbit_ah_home_odds": _f(xbit_ah),
            "verdict": verdict,
            "note": cc.get("note", ""),
        })
    save_cache(cache)
    return rows


def load_cache(path=None):
    p = path or CACHE_PATH
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cache(cache, path=None):
    p = path or CACHE_PATH
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--board", default=None)
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()
    print("cross-checking board (limit=%d)..." % args.limit)
    t0 = time.time()
    rows = crosscheck_board(args.board, limit=args.limit)
    dt = time.time() - t0
    counts = {"agree": 0, "disagree": 0, "no_fs": 0}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print()
    print("%-40s %-8s %-5s %6s %6s %6s %6s" % ("match", "verdict", "fs?", "fsOU", "xOU", "fsAH", "xAH"))
    print("-" * 84)
    for r in rows:
        fs_ou = "%.2f" % r["fs_ou_over_odds"] if r["fs_ou_over_odds"] is not None else "-"
        x_ou = "%.2f" % r["xbit_ou_over_odds"] if r["xbit_ou_over_odds"] is not None else "-"
        fs_ah = "%.2f" % r["fs_ah_home"] if r["fs_ah_home"] is not None else "-"
        x_ah = "%.2f" % r["xbit_ah_home_odds"] if r["xbit_ah_home_odds"] is not None else "-"
        name = r["match"]
        if len(name) > 40:
            name = name[:37] + "..."
        found = "Y" if r["fs_found"] else "N"
        print("%-40s %-8s %-5s %6s %6s %6s %6s" % (name, r["verdict"], found, fs_ou, x_ou, fs_ah, x_ah))
    print("-" * 84)
    print("summary: agree=%d disagree=%d no_fs=%d (%.1fs)" % (counts.get("agree", 0), counts.get("disagree", 0), counts.get("no_fs", 0), dt))
    print("cache: %s" % CACHE_PATH)


if __name__ == "__main__":
    main()