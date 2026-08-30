import asyncio
import concurrent.futures
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from model import (
    ah_ev,
    ah_ev_away,
    btts_prob,
    ev,
    fit_total_from_ou,
    lam_from_odds,
    lam_from_1x2,
    match_probs,
    over_prob,
    score_matrix,
    total_ev,
    under_prob,
)
import asyncio
import db
import settlement
import scraper_1xbit as sc
import scraper_historical as sh
try:
    import scraper_flashscore as fs
except ImportError:
    fs = None

db.init_db()

app = FastAPI(
    title="Football Betting Recommendation Engine API",
    description="Dixon-Coles bivariate Poisson recommendation engine and live scanner for football betting markets",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = os.path.join(BASE_DIR, "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

scan_state = {
    "is_running": False,
    "last_scan_time": None,
    "last_scan_count": 0,
    "last_scan_picks": 0,
    "error": None,
    "progress": "",
}


def load_config() -> Dict[str, Any]:
    cfg_path = os.path.join(BASE_DIR, "config.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "data_source": "1xbit",
        "scan_match_limit": 500,
        "filters": {
            "min_odds": 1.66,
            "min_ev": 0.0,
            "max_ah_abs_line": 1.5,
            "top_pick_limit": 40,
            "top_picks_per_market": 12,
            "top_picks_per_match": 2,
        },
        "markets": ["1x2", "ah", "ou", "btts"],
        "output": "picks.json",
        "historical": {"league": "E0", "season": "2526"},
        "tracking_unit": 1.0,
    }


def save_config(cfg: Dict[str, Any]) -> None:
    cfg_path = os.path.join(BASE_DIR, "config.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def load_picks_file() -> List[Dict[str, Any]]:
    picks_path = os.path.join(BASE_DIR, "picks.json")
    if os.path.exists(picks_path):
        try:
            with open(picks_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def load_detailed_matches() -> List[Dict[str, Any]]:
    matches_path = os.path.join(BASE_DIR, "matches_detailed.json")
    if os.path.exists(matches_path):
        try:
            with open(matches_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def execute_live_scan_sync():
    global scan_state
    scan_state["is_running"] = True
    scan_state["progress"] = "Fetching active matches from 1xbit..."
    scan_state["error"] = None
    try:
        cfg = load_config()
        min_odds = cfg.get("filters", {}).get("min_odds", 1.66)
        min_ev = cfg.get("filters", {}).get("min_ev", 0.0)
        max_ah_line = cfg.get("filters", {}).get("max_ah_abs_line", 2.5)
        window_hours = float(cfg.get("scan_window_hours", 16))

        if cfg.get("data_source") == "flashscore":
            if fs is None:
                raise RuntimeError("FlashScore source requires the optional Playwright dependency")
            leagues = cfg.get("flashscore_leagues", [])
            auto_discover = len(leagues) == 0
            raw_matches = asyncio.run(fs.list_matches(leagues, auto_discover))
            if len(raw_matches) == 0:
                scan_state["progress"] = "FlashScore returned no matches, falling back to 1xbit..."
                print("[LOG] FlashScore empty, falling back to 1xbit")
                raw_matches = sc.list_matches(count=int(cfg.get("scan_match_limit", 500)))
                scan_state["progress"] = f"Processing {len(raw_matches)} matches from 1xbit (fallback)..."
            else:
                scan_state["progress"] = f"Processing {len(raw_matches)} matches from FlashScore..."
                print(f"[LOG] FlashScore found {len(raw_matches)} matches")
        else:
            scan_match_limit = int(cfg.get("scan_match_limit", 500))
            raw_matches = sc.list_matches_paginated(count=scan_match_limit, window_hours=window_hours)
            scan_state["progress"] = f"Processing {len(raw_matches)} matches from 1xbit ({window_hours:g}h window)..."
            print(f"[LOG] 1xbit found {len(raw_matches)} matches in {window_hours:g}h window")
        scan_state["progress"] = f"Processing markets for {len(raw_matches)} matches..."

        def _fetch_one(m):
            try:
                v = sc.get_match(m["I"])
                return sc.extract_markets(v)
            except Exception:
                return None

        prefetched = []
        if cfg.get("data_source") != "flashscore" and len(raw_matches) > 30:
            workers = min(8, max(4, max(1, len(raw_matches)) // 40))
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
                prefetched = list(ex.map(_fetch_one, raw_matches))

        picks = []
        detailed_matches = []
        for i, m in enumerate(raw_matches):
            try:
                if cfg.get("data_source") == "flashscore":
                    odds = asyncio.run(fs.get_match_odds(m["I"]))
                    combined = {**m, "odds": odds}
                    o = fs.extract_markets(combined)
                else:
                    o = prefetched[i] if prefetched else _fetch_one(m)
                    if not o:
                        continue
                if not o["odds_1x2"] or 2.5 not in o["odds_ou"]:
                    continue
                o1, od, o2 = o["odds_1x2"][1], o["odds_1x2"][2], o["odds_1x2"][3]
                oov = o["odds_ou"][2.5][9]
                oun = o["odds_ou"][2.5][10]
                if oov and oun:
                    lh, la, fair_1x2 = lam_from_1x2(o1, od, o2)
                    _, fair_over = fit_total_from_ou(oov, oun, 2.5)
                else:
                    lh, la, fair_1x2, fair_over = 1.5, 1.2, [0.5, 0.3, 0.2], 0.55

                ph, pd, pa = match_probs(lh, la)
                pbt = btts_prob(lh, la)
                po = over_prob(2.5, lh, la)
                pu = under_prob(2.5, lh, la)

                from main import analyze_match
                m_picks = analyze_match(o, lh, la, min_odds, min_ev, max_ah_line)
                picks.extend(m_picks)

                matrix, _ = score_matrix(lh, la)
                top_scores = sorted(
                    [{"score": f"{x}-{y}", "prob": round(p, 4)} for (x, y), p in matrix.items()],
                    key=lambda s: s["prob"],
                    reverse=True,
                )[:6]

                detailed_matches.append({
                    "info": o,
                    "lambdas": {"home": round(lh, 3), "away": round(la, 3), "total": round(lh + la, 3)},
                    "fair_1x2": [round(x, 4) for x in fair_1x2],
                    "fair_over25": round(fair_over, 4),
                    "probs": {
                        "home": round(ph, 4),
                        "draw": round(pd, 4),
                        "away": round(pa, 4),
                        "btts": round(pbt, 4),
                        "over25": round(po, 4),
                        "under25": round(pu, 4),
                    },
                    "top_scores": top_scores,
                    "picks": m_picks,
                })
                time.sleep(0.08)
            except Exception as ex:
                pass

        from main import select_top_picks
        top_limit = int(cfg.get("filters", {}).get("top_pick_limit", 12))
        per_market = int(cfg.get("filters", {}).get("top_picks_per_market", 3))
        per_match = int(cfg.get("filters", {}).get("top_picks_per_match", 2))
        picks = select_top_picks(
            picks,
            limit=top_limit,
            per_market=per_market,
            per_match=per_match,
            min_ev=min_ev,
            min_edge=float(cfg.get("filters", {}).get("min_edge", 0.03)),
        )

        # Every published recommendation is immediately locked for ROI tracking.
        for pick in picks:
            _, created = db.insert_bet(pick)
            pick["newly_locked"] = created

        picks_path = os.path.join(BASE_DIR, "picks.json")
        with open(picks_path, "w", encoding="utf-8") as f:
            json.dump(picks, f, ensure_ascii=False, indent=2)

        detailed_path = os.path.join(BASE_DIR, "matches_detailed.json")
        with open(detailed_path, "w", encoding="utf-8") as f:
            json.dump(detailed_matches, f, ensure_ascii=False, indent=2)

        scan_state["last_scan_time"] = datetime.now(timezone.utc).isoformat()
        scan_state["last_scan_count"] = len(detailed_matches)
        scan_state["last_scan_picks"] = len(picks)
        scan_state["progress"] = "Scan completed successfully."
    except Exception as e:
        scan_state["error"] = str(e)
        scan_state["progress"] = f"Scan failed: {e}"
    finally:
        scan_state["is_running"] = False


@app.get("/")
def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"status": "ok", "message": "Football Recommendation Engine running. Deploy UI in static/."})


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Football Betting Recommendation Engine (FC)",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime": time.time(),
        "scan_state": scan_state,
        "config": load_config(),
    }


@app.get("/api/picks")
def get_picks(
    market: Optional[str] = Query(None, description="Filter by market: 1x2, ah, ou, btts"),
    league: Optional[str] = Query(None, description="Filter by league string"),
    min_odds: float = Query(1.66, ge=1.0, description="Minimum decimal odds floor"),
    max_odds: Optional[float] = Query(None, description="Maximum decimal odds cap"),
    min_ev: float = Query(0.0, description="Minimum expected value threshold"),
    search: Optional[str] = Query(None, description="Search query for team names or league"),
    sort_by: str = Query("rank_score", description="Sort field: rank_score, ev, odds, probability"),
    sort_order: str = Query("desc", description="Sort direction: asc, desc"),
):
    raw_picks = load_picks_file()
    cfg = load_config()
    from main import select_top_picks
    raw_picks = select_top_picks(
        raw_picks,
        limit=int(cfg.get("filters", {}).get("top_pick_limit", 12)),
        per_market=int(cfg.get("filters", {}).get("top_picks_per_market", 3)),
        per_match=int(cfg.get("filters", {}).get("top_picks_per_match", 2)),
        min_ev=float(cfg.get("filters", {}).get("min_ev", 0.0)),
        min_edge=float(cfg.get("filters", {}).get("min_edge", 0.03)),
    )

    filtered = []
    leagues_set = {
        match.get("info", {}).get("league")
        for match in load_detailed_matches()
        if match.get("info", {}).get("league")
    }
    markets_set = set()

    for p in raw_picks:
        if not isinstance(p, dict) or "odds" not in p or "ev" not in p:
            continue

        l = p.get("league")
        m = p.get("market")
        if l:
            leagues_set.add(l)
        if m:
            markets_set.add(m)

        odds = p.get("odds", 0.0)
        e = p.get("ev", 0.0)
        prob = p.get("probability", 0.0)

        # Enforce minimum odds floor (never below requested or 1.66)
        if odds < max(min_odds, 1.66):
            continue
        if max_odds is not None and odds > max_odds:
            continue
        if e < min_ev:
            continue
        if market and market.lower() != "all" and m and m.lower() != market.lower():
            continue
        if league and league.lower() != "all" and l and league.lower() not in l.lower():
            continue
        if search:
            q = search.lower()
            match_name = str(p.get("match", "")).lower()
            pick_name = str(p.get("pick", "")).lower()
            league_name = str(l or "").lower()
            if q not in match_name and q not in pick_name and q not in league_name:
                continue

        p_val = prob if prob else ((e + 1.0) / odds if odds > 0 else 0.0)

        item = dict(p)
        item["probability"] = round(p_val, 4)
        item["locked"] = True
        filtered.append(item)

    reverse = sort_order.lower() == "desc"
    if sort_by == "odds":
        filtered.sort(key=lambda x: x.get("odds", 0.0), reverse=reverse)
    elif sort_by == "probability":
        filtered.sort(key=lambda x: x.get("probability", 0.0), reverse=reverse)
    elif sort_by == "rank_score":
        filtered.sort(key=lambda x: x.get("rank_score", 0.0), reverse=reverse)
    elif sort_by == "start_ts":
        filtered.sort(key=lambda x: x.get("start_ts", 0), reverse=reverse)
    else:  # default 'ev'
        filtered.sort(key=lambda x: x.get("ev", 0.0), reverse=reverse)

    avg_ev = sum(x["ev"] for x in filtered) / len(filtered) if filtered else 0.0
    avg_odds = sum(x["odds"] for x in filtered) / len(filtered) if filtered else 0.0

    return {
        "summary": {
            "total_picks": len(raw_picks),
            "qualified_picks": len(filtered),
            "avg_ev_pct": round(avg_ev * 100, 2),
            "avg_odds": round(avg_odds, 3),
            "min_odds_floor": 1.66,
            "selection_limit": cfg.get("filters", {}).get("top_pick_limit", 12),
            "max_picks_per_match": cfg.get("filters", {}).get("top_picks_per_match", 2),
            "leagues": sorted(list(leagues_set)),
            "markets": sorted(list(markets_set)),
            "last_scan_time": scan_state.get("last_scan_time"),
        },
        "picks": filtered,
    }


@app.get("/api/matches")
def get_matches():
    matches = load_detailed_matches()
    return {"count": len(matches), "matches": matches}


@app.get("/api/tracker")
def get_tracker():
    now = time.time()

    def timing(bet):
        item = dict(bet)
        kickoff = float(item.get("start_ts") or 0)
        if item.get("settled"):
            item["timing_status"] = "settled"
        elif not kickoff:
            item["timing_status"] = "unknown"
        elif now < kickoff:
            item["timing_status"] = "not_started"
        elif now < kickoff + 3 * 60 * 60:
            item["timing_status"] = "awaiting_final"
        else:
            item["timing_status"] = "settlement_overdue"
        return item

    return {
        "summary": db.get_roi(),
        "locked": [timing(bet) for bet in db.get_unsettled()],
        "settled": [timing(bet) for bet in db.get_settled()],
        "market_performance": db.get_market_performance(),
        "unit_size": 1.0,
    }


@app.post("/api/settle")
def settle_locked_picks():
    try:
        result = settlement.settle_all()
        return {**result, "summary": db.get_roi()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Settlement refresh failed: {exc}")


@app.post("/api/scan")
def trigger_scan(background_tasks: BackgroundTasks):
    global scan_state
    if scan_state["is_running"]:
        return {"status": "busy", "message": "A scan is already in progress.", "state": scan_state}

    background_tasks.add_task(execute_live_scan_sync)
    return {"status": "started", "message": "Live scan triggered in background.", "state": scan_state}


@app.get("/api/scan/status")
def get_scan_status():
    return scan_state


class BacktestRequest(BaseModel):
    league: str = "E0"
    season: str = "2425"
    min_odds: float = 1.66
    min_ev: float = 0.02
    market_filter: Optional[str] = "all"


@app.post("/api/backtest")
def run_backtest(req: BacktestRequest):
    try:
        csv_path = sh.download(req.league, req.season)
        rows = sh.load_rows(csv_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch historical data: {str(e)}")

    normalized_rows = [sh.normalize(r) for r in rows if r.get("Date") and r.get("FTHG") is not None]

    from main import backtest_one

    matches_evaluated = []
    bets_placed = []
    equity_curve = [0.0]
    running_profit = 0.0

    market_stats: Dict[str, Dict[str, Any]] = {}

    for r in normalized_rows:
        if r["fthg"] is None or r["ftag"] is None:
            continue
        res = backtest_one(r, min_odds=req.min_odds, min_ev=req.min_ev)
        matches_evaluated.append(res)

        for p in res.get("picks", []):
            m = p.get("market")
            if req.market_filter and req.market_filter.lower() != "all" and m != req.market_filter.lower():
                continue

            odds = p["odds"]
            won = p["won"]
            profit = (odds - 1.0) if won else -1.0
            running_profit += profit
            equity_curve.append(round(running_profit, 2))

            bet_record = {
                "date": res["date"],
                "match": res["match"],
                "score": res["ft"],
                "market": m,
                "pick": p["pick"],
                "odds": odds,
                "ev": p["ev"],
                "won": won,
                "profit_unit": round(profit, 3),
                "running_equity": round(running_profit, 2),
            }
            bets_placed.append(bet_record)

            if m not in market_stats:
                market_stats[m] = {"bets": 0, "wins": 0, "profit": 0.0, "total_odds": 0.0}
            market_stats[m]["bets"] += 1
            if won:
                market_stats[m]["wins"] += 1
            market_stats[m]["profit"] += profit
            market_stats[m]["total_odds"] += odds

    total_bets = len(bets_placed)
    total_wins = sum(1 for b in bets_placed if b["won"])
    total_profit = sum(b["profit_unit"] for b in bets_placed)
    roi_pct = (total_profit / total_bets * 100) if total_bets > 0 else 0.0
    hit_rate = (total_wins / total_bets * 100) if total_bets > 0 else 0.0
    avg_odds = (sum(b["odds"] for b in bets_placed) / total_bets) if total_bets > 0 else 0.0

    market_breakdown = {}
    for m, st in market_stats.items():
        b_count = st["bets"]
        w_count = st["wins"]
        market_breakdown[m] = {
            "bets": b_count,
            "wins": w_count,
            "hit_rate_pct": round((w_count / b_count * 100) if b_count else 0.0, 2),
            "profit_units": round(st["profit"], 2),
            "roi_pct": round((st["profit"] / b_count * 100) if b_count else 0.0, 2),
            "avg_odds": round((st["total_odds"] / b_count) if b_count else 0.0, 2),
        }

    return {
        "league": req.league,
        "season": req.season,
        "total_matches": len(normalized_rows),
        "total_bets": total_bets,
        "total_wins": total_wins,
        "hit_rate_pct": round(hit_rate, 2),
        "total_profit_units": round(total_profit, 2),
        "roi_pct": round(roi_pct, 2),
        "avg_odds": round(avg_odds, 3),
        "profit_per_100": round(roi_pct, 2),
        "market_breakdown": market_breakdown,
        "equity_curve": equity_curve[:: max(1, len(equity_curve) // 100)],
        "recent_bets": bets_placed[-25:],
    }


class SimRequest(BaseModel):
    bankroll: float = 1000.0
    stake_pct: float = 0.02
    odds: float = 1.95
    probability: float = 0.58
    rounds: int = 200
    iterations: int = 1000
    strategy: str = "flat"


@app.post("/api/simulate")
def run_simulation(req: SimRequest):
    p = req.probability
    odds = req.odds
    b = odds - 1.0
    k = max(0.0, min((b * p - (1.0 - p)) / b if b > 0 else 0.0, 0.10))

    import random

    finals = []
    sample_trajectories = []

    for it in range(req.iterations):
        bank = req.bankroll
        traj = [bank]
        for r in range(req.rounds):
            stake = (k * bank) if req.strategy == "kelly" else (req.stake_pct * bank)
            won = random.random() < p
            bank += (b * stake) if won else -stake
            if it < 5 and r % max(1, req.rounds // 40) == 0:
                traj.append(round(bank, 2))
        finals.append(bank)
        if it < 5:
            traj.append(round(bank, 2))
            sample_trajectories.append(traj)

    finals.sort()
    n = len(finals)
    ev_val = p * odds - 1.0

    return {
        "ev_pct": round(ev_val * 100, 2),
        "kelly_pct": round(k * 100, 2),
        "median": round(finals[n // 2], 2),
        "p5_worst": round(finals[int(n * 0.05)], 2),
        "p95_best": round(finals[int(n * 0.95)], 2),
        "ruin_pct": round(100.0 * sum(1 for x in finals if x < req.bankroll * 0.5) / n, 2),
        "sample_trajectories": sample_trajectories,
    }


@app.get("/api/config")
def get_config():
    return load_config()


@app.post("/api/config")
def update_config(cfg: Dict[str, Any]):
    # Merge partial UI updates so breadth and selection safety controls cannot
    # silently disappear when an older browser form saves its visible fields.
    saved = load_config()
    merged = dict(saved)
    merged.update({key: value for key, value in cfg.items() if key != "filters"})
    merged_filters = dict(saved.get("filters", {}))
    merged_filters.update(cfg.get("filters", {}))
    merged["filters"] = merged_filters

    # Enforce minimum odds floor constraint of 1.66
    merged["filters"]["min_odds"] = max(float(merged["filters"].get("min_odds", 1.66)), 1.66)
    merged["filters"]["min_ev"] = max(float(merged["filters"].get("min_ev", 0.0)), 0.0)
    merged["filters"]["top_picks_per_match"] = min(
        2, max(1, int(merged["filters"].get("top_picks_per_match", 1)))
    )
    save_config(merged)
    return {"status": "saved", "config": load_config()}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"Starting Football Betting Recommendation Engine on http://{host}:{port}")
    uvicorn.run("server:app", host=host, port=port, reload=True)
