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


def get_match(mid, country=169):
    url = f"{BASE}GetGameZip?id={mid}&lng=en&country={country}"
    j = fetch(url)
    return j.get("Value", {})


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
    }
    for e in odds:
        t, c, g, p = e.get("T"), e.get("C"), e.get("G"), e.get("P")
        if g == 1 and t in (1, 2, 3):
            out["odds_1x2"][t] = c
        elif g == 17 and t in (9, 10) and p is not None:
            out["odds_ou"].setdefault(p, {})[t] = c
        elif g == 2 and t == 7 and p is not None:
            out["odds_ah"].setdefault("home", []).append((p, c))
        elif g == 2 and t == 8 and p is not None:
            out["odds_ah"].setdefault("away", []).append((p, c))
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