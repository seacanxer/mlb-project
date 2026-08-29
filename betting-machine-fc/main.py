import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model import (
    ah_ev,
    ah_ev_away,
    btts_prob,
    ev,
    lam_from_odds,
    lam_from_1x2,
    match_probs,
    over_prob,
    total_ev,
    under_prob,
)


def run_pipeline(cfg=None):
    if cfg is None:
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

    src = cfg.get("data_source", "1xbit")
    min_odds = cfg.get("filters", {}).get("min_odds", 1.66)
    min_ev = cfg.get("filters", {}).get("min_ev", 0.0)
    max_ah_line = cfg.get("filters", {}).get("max_ah_abs_line", 2.5)
    out_path = cfg.get("output", "picks.json")
    if not os.path.isabs(out_path):
        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), out_path)

    if src == "1xbit":
        import scraper_1xbit as sc

        matches = sc.list_matches()
        picks = []
        detailed_matches = []
        for m in matches:
            try:
                v = sc.get_match(m["I"])
                o = sc.extract_markets(v)
                if not o["odds_1x2"] or 2.5 not in o["odds_ou"]:
                    continue
                o1, od, o2 = o["odds_1x2"][1], o["odds_1x2"][2], o["odds_1x2"][3]
                oov = o["odds_ou"][2.5][9]
                oun = o["odds_ou"][2.5][10]
                lh, la, fair_1x2 = lam_from_1x2(o1, od, o2)
                _, fair_over = fit_total_from_ou(oov, oun, 2.5)
                m_picks = analyze_match(o, lh, la, min_odds, min_ev, max_ah_line=max_ah_line)
                picks.extend(m_picks)
                detailed_matches.append({
                    "info": o,
                    "lambdas": {"home": round(lh, 3), "away": round(la, 3), "total": round(lh + la, 3)},
                    "fair_1x2": [round(x, 4) for x in fair_1x2],
                    "fair_over25": round(fair_over, 4),
                    "picks": m_picks,
                })
            except Exception as e:
                picks.append({"match": m.get("I"), "error": str(e)})

        picks = select_top_picks(
            picks,
            limit=int(cfg.get("filters", {}).get("top_pick_limit", 12)),
            per_market=int(cfg.get("filters", {}).get("top_picks_per_market", 3)),
        )
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(picks, f, ensure_ascii=False, indent=2)

        detailed_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "matches_detailed.json")
        with open(detailed_path, "w", encoding="utf-8") as f:
            json.dump(detailed_matches, f, ensure_ascii=False, indent=2)

        summarize(picks)
        return picks
    elif src == "historical":
        import scraper_historical as sh

        league = cfg.get("historical", {}).get("league", "E0")
        season = cfg.get("historical", {}).get("season", "2526")
        rows = sh.load_rows(sh.download(league, season))
        results = []
        for r in map(sh.normalize, rows):
            if r["fthg"] is None:
                continue
            results.append(backtest_one(r, min_odds, min_ev))
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        summarize(results)
        return results
    else:
        raise SystemExit(f"unknown data_source: {src}")


def main():
    run_pipeline()


def analyze_match(o, lh, la, min_odds=1.66, min_ev=0.0, max_ah_line=2.5):
    out = []
    ph, pd, pa = match_probs(lh, la)
    pbt = btts_prob(lh, la)
    po = over_prob(2.5, lh, la)
    pu = under_prob(2.5, lh, la)
    o1, od, o2 = o["odds_1x2"][1], o["odds_1x2"][2], o["odds_1x2"][3]
    # 1X2
    for market, pick, p, odds in [
        ("1x2", f"Home ({o['home']})", ph, o1),
        ("1x2", "Draw", pd, od),
        ("1x2", f"Away ({o['away']})", pa, o2),
    ]:
        e = ev(p, odds) if odds else -999
        if e > min_ev and odds and odds >= min_odds:
            out.append(pick_entry(o, market, pick, p, odds, e))
    # O/U: evaluate every bookmaker line with the fitted goal distribution.
    # total_ev handles integer pushes and quarter-line half settlements correctly.
    for line, prices in (o.get("odds_ou") or {}).items():
        try:
            line_value = float(line)
        except (TypeError, ValueError):
            continue
        for side, pick, probability, odds in [
            ("over", f"Over {line_value:g}", over_prob(line_value, lh, la), prices.get(9)),
            ("under", f"Under {line_value:g}", under_prob(line_value, lh, la), prices.get(10)),
        ]:
            edge = total_ev(line_value, side, odds, lh, la) if odds else -999
            if odds and edge > min_ev and odds >= min_odds:
                out.append(pick_entry(o, "ou", pick, probability, odds, edge))
    # BTTS
    btts_market = o.get("odds_btts") or {}
    if isinstance(btts_market, (int, float)):
        btts_market = {"yes": btts_market}
    for pick, p, odds in [
        ("BTTS Yes", pbt, btts_market.get("yes")),
        ("BTTS No", 1.0 - pbt, btts_market.get("no")),
    ]:
        e = ev(p, odds) if odds else -999
        if odds and e > min_ev and odds >= min_odds:
            out.append(pick_entry(o, "btts", pick, p, odds, e))
    # AH
    for line, c in o.get("odds_ah", {}).get("home", []) or []:
        if abs(line) > max_ah_line:
            continue
        e_ah = ah_ev(line, c, lh, la)
        if c >= min_odds and e_ah > min_ev:
            p_approx = (e_ah + 1.0) / c if c > 0 else 0
            out.append(pick_entry(o, "ah", f"Home {line:+.2f}", p_approx, c, e_ah))
    for line, c in o.get("odds_ah", {}).get("away", []) or []:
        if abs(line) > max_ah_line:
            continue
        e_ah = ah_ev_away(line, c, lh, la)
        if c >= min_odds and e_ah > min_ev:
            p_approx = (e_ah + 1.0) / c if c > 0 else 0
            out.append(pick_entry(o, "ah", f"Away {line:+.2f}", p_approx, c, e_ah))
    return out


def select_top_picks(candidates, limit=12, per_market=3):
    """Create a small, diversified parlay shortlist instead of returning every edge.

    Gates reject low-confidence longshots and implausibly large model/market gaps.
    Only one selection per fixture is retained, then market caps provide variety.
    """
    probability_floor = {"1x2": 0.42, "ah": 0.50, "ou": 0.52, "btts": 0.52}
    eligible = []
    for pick in candidates:
        market = pick.get("market")
        probability = float(pick.get("probability") or 0)
        odds = float(pick.get("odds") or 0)
        edge = float(pick.get("ev") or 0)
        if market not in probability_floor:
            continue
        if probability < probability_floor[market] or not 1.66 <= odds <= 3.50:
            continue
        if edge < 0.02 or edge > 0.35:
            continue
        # Probability drives the rank; EV helps only within a capped sane range.
        score = probability * 70 + min(edge, 0.15) / 0.15 * 30
        item = dict(pick)
        item["rank_score"] = round(score, 2)
        item["locked"] = True
        eligible.append(item)

    eligible.sort(key=lambda p: (p["rank_score"], p["probability"]), reverse=True)
    selected, seen_matches, market_counts = [], set(), {}
    for pick in eligible:
        match_key = (pick.get("match"), pick.get("start_ts"))
        market = pick["market"]
        if match_key in seen_matches or market_counts.get(market, 0) >= per_market:
            continue
        selected.append(pick)
        seen_matches.add(match_key)
        market_counts[market] = market_counts.get(market, 0) + 1
        if len(selected) >= limit:
            break
    return selected


def pick_entry(o, market, pick, p, odds, e):
    b = odds - 1.0
    p_val = p if p is not None else ((e + 1.0) / odds if odds > 0 else 0.0)
    kelly = max(0.0, min((b * p_val - (1.0 - p_val)) / b if b > 0 else 0.0, 0.10)) if p_val else 0.0
    return {
        "match_id": o.get("match_id"),
        "match": f"{o['home']} vs {o['away']}",
        "home": o.get("home"),
        "away": o.get("away"),
        "league": o.get("league"),
        "start_ts": o.get("start_ts"),
        "market": market,
        "pick": pick,
        "probability": round(p_val, 4),
        "odds": round(odds, 3),
        "ev": round(e, 4),
        "kelly_pct": round(kelly * 100, 2),
    }


def backtest_one(r, min_odds=1.66, min_ev=0.0):
    o1, od, o2 = r["odds_home"], r["odds_draw"], r["odds_away"]
    oov, oun = r["odds_over"], r["odds_under"]
    fthg, ftag = r["fthg"], r["ftag"]
    total = fthg + ftag
    margin = fthg - ftag
    lh, la, _, _ = lam_from_odds(o1, od, o2, oov, oun, 2.5)
    ph, pd, pa = match_probs(lh, la)
    pbt = btts_prob(lh, la)
    po = over_prob(2.5, lh, la)
    pu = under_prob(2.5, lh, la)
    res = {
        "date": r["date"],
        "match": f"{r['home']} vs {r['away']}",
        "ft": f"{fthg}-{ftag}",
        "lambdas": {"home": round(lh, 3), "away": round(la, 3)},
        "probs": {"home": round(ph, 3), "draw": round(pd, 3), "away": round(pa, 3), "btts": round(pbt, 3), "over25": round(po, 3)},
        "picks": [],
    }
    cands = [
        ("1x2", "Home", ph, r["odds_home"], margin > 0),
        ("1x2", "Draw", pd, r["odds_draw"], margin == 0),
        ("1x2", "Away", pa, r["odds_away"], margin < 0),
        ("ou", "Over 2.5", po, r["odds_over"], total > 2),
        ("ou", "Under 2.5", pu, r["odds_under"], total < 2),
        ("btts", "BTTS Yes", pbt, None, fthg >= 1 and ftag >= 1),
    ]
    for market, pick, p, odds, won in cands:
        if odds is None:
            continue
        e = ev(p, odds)
        if e > min_ev and odds >= min_odds:
            res["picks"].append({"market": market, "pick": pick, "odds": round(odds, 3), "ev": round(e, 4), "won": won})
    res["n_picks"] = len(res["picks"])
    res["hit_rate"] = round(sum(1 for p in res["picks"] if p["won"]) / res["n_picks"], 3) if res["n_picks"] else None
    return res


def summarize(items):
    picks = [p for p in items if p.get("market")]
    print(f"total matches: {len(items)}")
    print(f"qualified picks (EV>{0}, odds>={1.66}): {len(picks)}")
    for p in picks[:15]:
        print(f"  {p['match'][:38]:38s} {p['market']:7s} {str(p['pick'])[:24]:24s} odds={p['odds']:.2f} EV={p['ev']:+.3f}")


if __name__ == "__main__":
    main()
