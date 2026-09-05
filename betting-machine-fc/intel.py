"""Market intelligence board — Parlindunganup-style analysis (PRD v2).

Workflow replicated:
1. probability 1X2 + expected home/away/total + goal difference
2. read opening line + O/U and AH movement
3. consensus vs disagreement across bookmakers (1xbit only -> limited)
4. match context notes
5. pick a more defensive line than raw model output
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from model import (
    btts_prob,
    match_probs,
    over_prob,
    score_matrix,
    total_ev,
    total_fair_odds,
    under_prob,
)
from prediction import build_projection, select_main_ah, select_main_ou
from league_profiles import get_league_profile
import db

BOARD_PATH = os.path.join(BASE_DIR, "intel_board.json")
MIN_REC_ODDS = 1.75
MIN_DEFENSIVE_PROB = 0.55


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _line_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def analyze_intel(o, snapshots=None):
    match_id = str(o.get("match_id") or "")
    league = o.get("league") or ""
    profile = get_league_profile(league)
    item = {
        "match_id": match_id,
        "home": o.get("home"),
        "away": o.get("away"),
        "league": league,
        "start_ts": o.get("start_ts"),
        "kickoff_utc": datetime.fromtimestamp(float(o.get("start_ts") or 0), timezone.utc).isoformat()
        if o.get("start_ts") else None,
        "coverage": profile.route,
        "data_grade": profile.data_grade,
        "league_model": profile.key,
        "coverage_reason": profile.reason,
        "recommendation": None,
        "decision": "NO BET",
        "decide_reason": "",
        "context": [],
    }
    try:
        proj = build_projection(o)
    except Exception as e:
        item["skip"] = True
        item["decision"] = "UNSUPPORTED"
        item["decide_reason"] = f"incomplete market or engine error: {e}"
        return item

    lh, la = proj["home"], proj["away"]
    total = lh + la
    ph, pd, pa = match_probs(lh, la)
    pbt = btts_prob(lh, la)
    matrix, _ = score_matrix(lh, la)
    top_scores = sorted(
        [{"score": f"{x}-{y}", "prob": round(p, 4)} for (x, y), p in matrix.items()],
        key=lambda s: s["prob"], reverse=True,
    )[:6]

    item.update({
        "lambdas": {"home": round(lh, 3), "away": round(la, 3), "total": round(total, 3),
                    "goal_diff": round(lh - la, 3)},
        "probs": {"home": round(ph, 4), "draw": round(pd, 4), "away": round(pa, 4),
                  "btts": round(pbt, 4), "over25": round(over_prob(2.5, lh, la), 4),
                  "under25": round(under_prob(2.5, lh, la), 4)},
        "top_scores": top_scores,
        "market_total": proj.get("market_total"),
        "market_margin": proj.get("market_margin"),
        "fair_1x2": [round(x, 4) for x in proj.get("fair_1x2", [])],
        "lambda_source": proj.get("lambda_source"),
        "market_total_line": proj.get("market_total_line"),
        "market_ah_line": proj.get("market_ah_line"),
    })

    # Main O/U line with movement
    main_ou = select_main_ou(o.get("odds_ou"))
    ou_movement = None
    if main_ou:
        ou_line, ou_over, ou_under = main_ou
        ou_movement = {
            "line": ou_line,
            "over_odds": ou_over,
            "under_odds": ou_under,
            "fair_over": round(proj.get("fair_over") or (1.0 / ou_over if ou_over else 0.0), 4),
        }
        if snapshots and match_id:
            ou_movement["over_mvt_pct"] = movement_pct(
                snapshots.get((match_id, "ou", ou_line, "over")),
                ou_over,
            )
            ou_movement["under_mvt_pct"] = movement_pct(
                snapshots.get((match_id, "ou", ou_line, "under")),
                ou_under,
            )
    item["main_ou"] = ou_movement

    # Main AH line with movement
    main_ah = select_main_ah(o.get("odds_ah"))
    ah_movement = None
    if main_ah:
        h_line, h_odds, a_line, a_odds = main_ah
        ah_movement = {"home_line": h_line, "home_odds": h_odds,
                       "away_line": a_line, "away_odds": a_odds}
        if snapshots and match_id:
            ah_movement["home_mvt_pct"] = movement_pct(
                snapshots.get((match_id, "ah", h_line, "home")), h_odds)
            ah_movement["away_mvt_pct"] = movement_pct(
                snapshots.get((match_id, "ah", a_line, "away")), a_odds)
    item["main_ah"] = ah_movement

    # Recommendation: defensive line (higher win prob) with min odds + positive EV
    rec = recommend_defensive(o, lh, la)
    item["recommendation"] = rec
    proj_coverage = proj.get("coverage_status", "market_only")
    item["decision"], item["decide_reason"] = decide(rec, proj_coverage, o)
    return item


def movement_pct(open_odds, current_odds):
    """Positive = odds lengthen (price moved against); negative = odds shorten."""
    if not open_odds or not current_odds:
        return None
    try:
        return round((1.0 / current_odds - 1.0 / open_odds) * 100.0, 2)
    except (TypeError, ZeroDivisionError):
        return None


def recommend_defensive(o, lh, la):
    """Pick the most defensible over/under line: prob >= MIN_DEFENSIVE_PROB,
    odds >= MIN_REC_ODDS, best EV. Falls back to AH if O/U has no edge."""
    best = None
    for raw_line, prices in (o.get("odds_ou") or {}).items():
        line = _line_float(raw_line)
        if line is None:
            continue
        try:
            over_odds = float(prices.get(9))
            under_odds = float(prices.get(10))
        except (TypeError, ValueError):
            continue
        candidates = []
        if over_odds and over_odds >= MIN_REC_ODDS:
            p_over = over_prob(line, lh, la)
            ev_over = total_ev(line, "over", over_odds, lh, la)
            if p_over >= MIN_DEFENSIVE_PROB:
                candidates.append(("over", over_odds, p_over, ev_over))
        if under_odds and under_odds >= MIN_REC_ODDS:
            p_under = under_prob(line, lh, la)
            ev_under = total_ev(line, "under", under_odds, lh, la)
            if p_under >= MIN_DEFENSIVE_PROB:
                candidates.append(("under", under_odds, p_under, ev_under))
        for side, odds, prob, ev in candidates:
            fair = total_fair_odds(line, side, lh, la)
            score = (ev, prob)
            if best is None or score > best["_score"]:
                best = {
                    "market": "ou",
                    "pick": f"{side.title()} {line:g}",
                    "line": line,
                    "side": side,
                    "odds": round(odds, 3),
                    "ev": round(ev, 4),
                    "prob": round(prob, 4),
                    "fair_odds": round(fair, 3) if fair and fair < 100 else None,
                    "reason": f"defensive O/U line, model total {lh+la:.2f}",
                    "_score": score,
                }
    if best is None:
        return None
    best.pop("_score", None)
    return best


def decide(rec, coverage, o):
    if coverage == "blocked":
        return "UNSUPPORTED", f"league route blocked: {get_league_profile(o.get('league')).reason}"
    if coverage == "market_only":
        return "NO BET", "market-only coverage — no team-rating support"
    if rec is None:
        return "NO BET", "no defensive line meets min-odds/probability gate"
    if rec["ev"] <= 0:
        return "NO BET", "no positive EV at defensive line"
    if coverage == "full":
        # single bookmaker -> circular price risk, cap at WATCH per PRD FR-5
        return "WATCH", "signal present; single-bookmaker reference (circular risk)"
    if coverage == "shadow":
        return "SHADOW", "shadow-coverage league recorded for evaluation"
    return "UNSUPPORTED", "no validated league model"


def load_board():
    if os.path.exists(BOARD_PATH):
        try:
            with open(BOARD_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"generated_at": None, "count": 0, "board": [], "error": "board not generated yet"}


def scan_intel(window_hours=16, max_matches=400, progress=None):
    import scraper_1xbit as sc

    raw = sc.list_matches_paginated(count=max_matches, window_hours=window_hours)

    def _fetch(m):
        try:
            v = sc.get_match(m["I"])
            if not v:
                return None
            return sc.extract_markets(v)
        except Exception:
            return None

    markets = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, o in enumerate(ex.map(_fetch, raw)):
            if o:
                markets.append(o)
            if progress and i % 50 == 0:
                progress(f"fetched {i}/{len(raw)}")

    snapshots = db_load_snapshots()
    board = []
    for o in markets:
        item = analyze_intel(o, snapshots=snapshots)
        if item.get("skip"):
            continue
        if item["match_id"]:
            save_snapshots(o)
            item["context"] = db.get_intel_context(item["match_id"])
        board.append(item)

    board.sort(key=lambda x: x.get("start_ts") or 0)
    payload = {
        "generated_at": now_iso(),
        "count": len(board),
        "window_hours": window_hours,
        "board": board,
    }
    with open(BOARD_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


def save_snapshots(o):
    match_id = str(o.get("match_id") or "")
    if not match_id:
        return
    observed_at = now_iso()
    for line, prices in (o.get("odds_ou") or {}).items():
        for side, key in (("over", 9), ("under", 10)):
            try:
                odds = float(prices.get(key))
                if odds and odds > 1.0:
                    db.save_intel_snapshot(match_id, o.get("home"), o.get("away"),
                                           o.get("league"), o.get("start_ts"),
                                           observed_at, "ou", float(line), side, odds)
            except (TypeError, ValueError):
                continue
    for side, key, lines in (("home", 0, o.get("odds_ah", {}).get("home") or []),
                             ("away", 0, o.get("odds_ah", {}).get("away") or [])):
        for line, odds in lines:
            try:
                if odds and float(odds) > 1.0:
                    db.save_intel_snapshot(match_id, o.get("home"), o.get("away"),
                                           o.get("league"), o.get("start_ts"),
                                           observed_at, "ah", float(line), side, float(odds))
            except (TypeError, ValueError):
                continue


def db_load_snapshots():
    """Return {(match_id, market, line, side): opening_odds} for movement."""
    opening = {}
    for row in db.get_intel_openings():
        key = (row["match_id"], row["market"], row["line"], row["side"])
        opening[key] = row["odds"]
    return opening