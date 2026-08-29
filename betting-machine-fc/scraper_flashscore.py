import asyncio
import json
import re
import time
from playwright.async_api import async_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

def parse_feed(body):
    result = {}
    for item in body.split('¬'):
        if not item:
            continue
        parts = item.split('÷')
        if len(parts) == 2:
            key, val = parts[0], parts[1]
            result[key] = val
    return result

async def fetch_feed(feed_url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 720})
        page = await context.new_page()
        feed_data = None
        async def on_response(response):
            nonlocal feed_data
            if response.url == feed_url and response.status == 200:
                feed_data = await response.text()
        page.on('response', on_response)
        await page.goto("https://www.flashscore.com/")
        await page.wait_for_timeout(2000)
        await page.goto(feed_url)
        await page.wait_for_timeout(2000)
        await browser.close()
        return feed_data

async def fetch_tournament_feed(tid):
    url = f"https://global.flashscore.ninja/2/x/feed/c_1_{tid}_8_en_y_1"
    return await fetch_feed(url)

async def discover_all_tournaments():
    feed = await fetch_feed("https://global.flashscore.ninja/2/x/feed/mc_8")
    if not feed:
        return []
    parsed = parse_feed(feed)
    leagues = []
    for key, val in parsed.items():
        if key.startswith("EC") and val:
            parts = val.split('¬')
            data = {}
            for p in parts:
                if not p:
                    continue
                kv = p.split('÷')
                if len(kv) == 2:
                    data[kv[0]] = kv[1]
            tid = data.get("ZB")
            name = data.get("ZA")
            if tid and name:
                leagues.append({"tournament_id": int(tid), "name": name})
    return leagues

async def list_matches(leagues=None, auto_discover=False):
    if not leagues and auto_discover:
        leagues = await discover_all_tournaments()
    if not leagues:
        return []
    matches = []
    for league in leagues:
        tid = league.get("tournament_id")
        if not tid:
            continue
        feed = await fetch_tournament_feed(tid)
        if not feed:
            continue
        parsed = parse_feed(feed)
        for key, val in parsed.items():
            if key.startswith("AA") and val:
                parts = val.split('¬')
                match_data = {}
                for p in parts:
                    if not p:
                        continue
                    kv = p.split('÷')
                    if len(kv) == 2:
                        match_data[kv[0]] = kv[1]
                match_id = match_data.get("PX")
                if not match_id:
                    continue
                matches.append({
                    "I": match_id,
                    "O1": match_data.get("AE", ""),
                    "O2": match_data.get("FH", ""),
                    "S": int(match_data.get("AD", 0)),
                    "L": league.get("name", "Unknown"),
                    "WP": match_data.get("WN", ""),
                })
    return matches

async def get_match_odds(match_id):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=UA)
        page = await context.new_page()
        url = f"https://www.flashscore.com/match/{match_id}/"
        await page.goto(url)
        await page.wait_for_timeout(3000)
        html = await page.content()
        await browser.close()
        odds_1x2 = {}
        odds_ou = {}
        odds_ah = {}
        odds_btts = None
        match_1x2 = re.findall(r'data-odds[_-]?(?:home|draw|away)="([\d.]+)"', html)
        if len(match_1x2) >= 3:
            odds_1x2 = {1: float(match_1x2[0]), 2: float(match_1x2[1]), 3: float(match_1x2[2])}
        over = re.search(r'data-odds-over-2\.5="([\d.]+)"', html)
        under = re.search(r'data-odds-under-2\.5="([\d.]+)"', html)
        if over and under:
            odds_ou[2.5] = {9: float(over.group(1)), 10: float(under.group(1))}
        ah_home = re.findall(r'data-odds-ah-home-([\d.]+)="([\d.]+)"', html)
        ah_away = re.findall(r'data-odds-ah-away-([\d.]+)="([\d.]+)"', html)
        for line, odds in ah_home:
            odds_ah.setdefault("home", []).append((float(line), float(odds)))
        for line, odds in ah_away:
            odds_ah.setdefault("away", []).append((float(line), float(odds)))
        btts = re.search(r'data-odds-btts-yes="([\d.]+)"', html)
        if btts:
            odds_btts = float(btts.group(1))
        return {"odds_1x2": odds_1x2, "odds_ou": odds_ou, "odds_ah": odds_ah, "odds_btts": odds_btts}

def extract_markets(v):
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
        "odds_btts": None,
    }
    odds = v.get("odds", {})
    out["odds_1x2"] = odds.get("odds_1x2", {})
    out["odds_ou"] = odds.get("odds_ou", {})
    out["odds_ah"] = odds.get("odds_ah", {})
    out["odds_btts"] = odds.get("odds_btts")
    return out

def scrape_all(leagues=None, auto_discover=True, delay=0.5, to_json="odds_live_flashscore.json"):
    rows = []
    matches = asyncio.run(list_matches(leagues, auto_discover))
    for m in matches:
        try:
            odds = asyncio.run(get_match_odds(m["I"]))
            m["odds"] = odds
            rows.append(extract_markets(m))
            time.sleep(delay)
        except Exception as e:
            rows.append({"match_id": m.get("I"), "error": str(e)})
    if to_json:
        with open(to_json, "w") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
    return rows

if __name__ == "__main__":
    out = scrape_all(auto_discover=True)
    print(f"scraped {len(out)} matches")
    for o in out[:5]:
        print(o.get("league"), "|", o.get("home"), "vs", o.get("away"), "| 1X2:", o.get("odds_1x2"))