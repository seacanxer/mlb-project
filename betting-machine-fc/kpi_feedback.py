import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

DB_PATH = "/home/ubuntu/mlb-project/betting-machine-fc/bets.db"

LEAGUE_COVERAGE = {
    "full": (
        "england. premier league", "england. championship", "england. league one",
        "england. league two", "england. premier league 2",
        "spain. la liga", "spain. segunda division",
        "italy. serie a", "italy. serie b",
        "germany. bundesliga", "germany. 2. bundesliga", "germany. 3 liga",
        "netherlands. eredivisie",
        "portugal. primeira liga", "portugal. liga portugal", "portugal. primeira liga",
        "turkey. superlig", "turkey. super lig",
        "france. ligue 1", "france. ligue 2",
        "greece. superleague", "belgium. jupiler league", "scotland. premiership",
        "austria. bundesliga", "switzerland. super league", "denmark. superliga",
        "sweden. allsvenskan", "norway. eliteserien", "poland. ekstraklasa",
        "russia. premier league", "ukraine. premier league", "czech republic. chance liga",
        "romania. liga 1", "croatia. hnl", "serbia. superlig",
    ),
    "shadow": (
        "usa. mls", "brazil. campeonato brasileiro", "brazil. serie a",
        "mexico. liga mx", "japan. j1 league", "japan. j-league",
        "argentina. primera", "colombia. primera a", "chile. primera division",
        "usa. usl", "canada. premier league", "south korea. k league 1",
        "china. super league", "australia. a-league", "saudi arabia. saudi professional league",
        "india. indian super league", "norway. eliteserien",
    ),
}

ODDS_BANDS = (
    ("under_1.75", 0.0, 1.75),
    ("1.75-2.00", 1.75, 2.0),
    ("2.00-2.50", 2.0, 2.5),
    ("over_2.50", 2.5, float("inf")),
)

DECISION_RULES = (
    ("top_pick", 0.6, float("inf")),
    ("official", 0.55, 0.6),
    ("watch", float("-inf"), 0.55),
)


def _coverage_for(league):
    key = (league or "").strip().lower()
    for candidate in LEAGUE_COVERAGE["full"]:
        if candidate in key or key in candidate:
            return "full"
    for candidate in LEAGUE_COVERAGE["shadow"]:
        if candidate in key or key in candidate:
            return "shadow"
    return "market_only"


def _odds_band(odds):
    for name, lo, hi in ODDS_BANDS:
        if lo <= odds < hi:
            return name
    return "over_2.50"


def _decision(probability, market):
    for name, lo, hi in DECISION_RULES:
        if lo <= probability < hi:
            return name
    return "watch"


def _blank_bucket(total=0, settled=0, wins=0, losses=0, pushes=0, profit=0.0):
    return {
        "total": total,
        "settled": settled,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "win_rate": None,
        "profit_units": round(profit, 4),
        "roi_pct": None,
    }


def _finalize(bucket):
    settled = bucket["settled"]
    if settled:
        bucket["win_rate"] = round(bucket["wins"] / max(settled - bucket["pushes"], 1), 4) if settled > bucket["pushes"] else None
        bucket["roi_pct"] = round(100.0 * bucket["profit_units"] / settled, 2)
    return bucket


def _add_row(bucket, won, profit):
    bucket["total"] += 1
    bucket["settled"] += 1
    if won == 1:
        bucket["wins"] += 1
    elif won == 0:
        bucket["losses"] += 1
    else:
        bucket["pushes"] += 1
    if profit is not None:
        bucket["profit_units"] += profit


def compute_kpis(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT market, league, odds, probability, won, profit, settled FROM bets"
    ).fetchall()
    settled_rows = [r for r in rows if r["settled"] == 1]

    categories = defaultdict(lambda: _blank_bucket())
    markets = defaultdict(lambda: _blank_bucket())
    leagues = defaultdict(lambda: _blank_bucket())
    odds_bands = defaultdict(lambda: _blank_bucket())
    decisions = defaultdict(lambda: _blank_bucket())
    overall = _blank_bucket()
    pending = sum(1 for r in rows if not r["settled"])

    for r in settled_rows:
        market = r["market"] or "unknown"
        league = r["league"] or "unknown"
        band = _odds_band(r["odds"]) if r["odds"] is not None else "unknown"
        prob = r["probability"] if r["probability"] is not None else 0.0
        decision = _decision(prob, market)
        won, profit = r["won"], r["profit"]
        for bucket in (overall, categories["all"], markets[market], leagues[league],
                       odds_bands[band], decisions[decision], categories[decision]):
            _add_row(bucket, won, profit)

    def _dump(buckets):
        return {k: _finalize(v) for k, v in sorted(buckets.items())}

    return {
        "categories": _dump(categories),
        "markets": _dump(markets),
        "leagues": _dump(leagues),
        "odds_bands": _dump(odds_bands),
        "decisions": _dump(decisions),
        "overall": _finalize(overall),
        "pending": pending,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _coverage_key(league):
    cover = _coverage_for(league)
    return cover


def backfill_kpis(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS bet_kpis ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "bet_id INTEGER UNIQUE NOT NULL, "
        "coverage_status TEXT NOT NULL, "
        "market TEXT, "
        "league TEXT, "
        "odds_band TEXT, "
        "won INTEGER, "
        "profit REAL, "
        "settled_at TEXT)"
    )
    rows = conn.execute(
        "SELECT id, market, league, odds, won, profit, settled_at FROM bets WHERE settled=1"
    ).fetchall()
    inserted = 0
    for bet_id, market, league, odds, won, profit, settled_at in rows:
        band = _odds_band(odds) if odds is not None else "unknown"
        cover = _coverage_key(league)
        conn.execute(
            "INSERT OR REPLACE INTO bet_kpis "
            "(bet_id, coverage_status, market, league, odds_band, won, profit, settled_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (bet_id, cover, market, league, band, won, profit, settled_at),
        )
        inserted += 1
    conn.commit()
    conn.close()
    return inserted


def get_kpis_api(db_path=DB_PATH):
    return json.dumps(compute_kpis(db_path), indent=2)


if __name__ == "__main__":
    n = backfill_kpis()
    kpis = compute_kpis()
    o = kpis["overall"]
    print(f"backfilled {n} rows into bet_kpis")
    print(f"overall: settled={o['settled']} wins={o['wins']} losses={o['losses']} "
          f"pushes={o['pushes']} win_rate={o['win_rate']} profit={o['profit_units']}u "
          f"roi={o['roi_pct']}%")
    print("per market:")
    for m, b in kpis["markets"].items():
        print(f"  {m:6s}: settled={b['settled']:4d} win_rate={b['win_rate']} roi={b['roi_pct']}% "
              f"profit={b['profit_units']}u")
    print("per odds band:")
    for m, b in kpis["odds_bands"].items():
        print(f"  {m:12s}: settled={b['settled']:4d} win_rate={b['win_rate']} roi={b['roi_pct']}% "
              f"profit={b['profit_units']}u")
    print("per decision category:")
    for m, b in kpis["decisions"].items():
        print(f"  {m:8s}: settled={b['settled']:4d} win_rate={b['win_rate']} roi={b['roi_pct']}% "
              f"profit={b['profit_units']}u")
    print(f"top leagues by settled:")
    top = sorted(kpis["leagues"].items(), key=lambda kv: kv[1]["settled"], reverse=True)[:8]
    for m, b in top:
        print(f"  {m:45s}: settled={b['settled']:3d} win_rate={b['win_rate']} roi={b['roi_pct']}%")
    print(f"pending bets: {kpis['pending']}")