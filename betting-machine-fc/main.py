import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model import (
    ah_ev,
    ah_ev_away,
    ah_fair_odds,
    ah_payout,
    ah_payout_away,
    btts_prob,
    devig,
    ev,
    match_probs,
    over_prob,
    total_fair_odds,
    total_ev,
    under_prob,
)
from fatigue import apply_rest_adjustment, record_fixtures
from prediction import build_projection, projection_candidate_status
from strength_rating import parse_fd_date


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
        from fatigue import load_ledger, save_ledger

        matches = sc.list_matches()
        picks = []
        detailed_matches = []
        _ledger = load_ledger()
        for m in matches:
            try:
                v = sc.get_match(m["I"])
                o = sc.extract_markets(v)
                projection = build_projection(
                    o,
                    strength_weight=cfg.get("formula", {}).get("strength_weight_override"),
                )
                lh, la = projection["home"], projection["away"]
                try:
                    lh, la, _f = apply_rest_adjustment(
                        o.get("home"), o.get("away"), o.get("start_ts"), lh, la, _ledger)
                    record_fixtures(_ledger, [(o.get("home"), o.get("away"), o.get("start_ts"))])
                except Exception:
                    pass
                m_picks = analyze_match(
                    o, lh, la, min_odds, min_ev, max_ah_line=max_ah_line,
                    projection_meta=projection,
                    active_markets=cfg.get("markets", ["ou", "ah"]),
                )
                picks.extend(m_picks)
                detailed_matches.append({
                    "info": o,
                    "lambdas": {"home": round(lh, 3), "away": round(la, 3), "total": round(lh + la, 3)},
                    "fair_1x2": [round(x, 4) for x in projection["fair_1x2"]],
                    "fair_over25": round(projection["fair_over"], 4),
                    "model": projection,
                    "picks": m_picks,
                })
            except Exception as e:
                picks.append({"match": m.get("I"), "error": str(e)})

        picks = select_top_picks(
            picks,
            limit=int(cfg.get("filters", {}).get("top_pick_limit", 12)),
            per_market=int(cfg.get("filters", {}).get("top_picks_per_market", 3)),
            per_match=int(cfg.get("filters", {}).get("top_picks_per_match", 2)),
            min_ev=float(min_ev),
            min_edge=float(cfg.get("filters", {}).get("min_edge", 0.03)),
            min_odds=float(cfg.get("filters", {}).get("min_odds", 1.66)),
            max_odds=cfg.get("filters", {}).get("max_odds"),
            top_signal_limit=int(cfg.get("filters", {}).get("top_signal_limit", 5)),
        )
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(picks, f, ensure_ascii=False, indent=2)

        detailed_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "matches_detailed.json")
        with open(detailed_path, "w", encoding="utf-8") as f:
            json.dump(detailed_matches, f, ensure_ascii=False, indent=2)

        try:
            from fatigue import save_ledger
            save_ledger(_ledger)
        except Exception:
            pass
        summarize(picks)
        return picks
    elif src == "historical":
        import scraper_historical as sh
        from strength_rating import prev_season_code

        league = cfg.get("historical", {}).get("league", "E0")
        season = cfg.get("historical", {}).get("season", "2526")
        rows = sh.load_rows(sh.download(league, season))
        results = []
        # OOS discipline: ratings from PREVIOUS season only (no lookahead);
        # ephemeral fatigue ledger in chronological order.
        bt_season = prev_season_code(season)
        bt_ledger = {}
        normed = sorted(
            (r for r in map(sh.normalize, rows) if r["fthg"] is not None),
            key=lambda r: (r.get("date") or ""),
        )
        for r in normed:
            results.append(backtest_one(
                r, min_odds, min_ev, ledger=bt_ledger,
                league_code=league, rating_season=bt_season,
                strength_weight=cfg.get("formula", {}).get("strength_weight_override")))
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        summarize(results)
        return results
    else:
        raise SystemExit(f"unknown data_source: {src}")


def main():
    run_pipeline()


def analyze_match(o, lh, la, min_odds=1.66, min_ev=0.0, max_ah_line=2.5,
                  projection_meta=None, active_markets=None):
    out = []
    active_markets = set(active_markets or ("ou", "ah"))
    projection_meta = projection_meta or {
        "formula_version": "legacy-test",
        "lambda_source": "test",
        "coverage_status": "full",
        "data_grade": "A",
    }
    ph, pd, pa = match_probs(lh, la)
    pbt = btts_prob(lh, la)
    po = over_prob(2.5, lh, la)
    pu = under_prob(2.5, lh, la)
    def market_value(mapping, key):
        return mapping.get(key, mapping.get(str(key)))

    o1, od, o2 = (market_value(o["odds_1x2"], key) for key in (1, 2, 3))
    market_1x2 = devig({"home": o1, "draw": od, "away": o2})
    # 1X2 — circular (experimental), gate lebih ketat di select_top_picks
    for market, pick, p, odds, market_p in [
        ("1x2", f"Home ({o['home']})", ph, o1, market_1x2.get("home")),
        ("1x2", "Draw", pd, od, market_1x2.get("draw")),
        ("1x2", f"Away ({o['away']})", pa, o2, market_1x2.get("away")),
    ]:
        if "1x2" not in active_markets:
            continue
        e = ev(p, odds) if odds else -999
        if e >= min_ev and odds and odds >= min_odds and odds <= 2.20:
            item = pick_entry(o, market, pick, p, odds, e, market_p, projection_meta=projection_meta)
            item["independent_signal"] = False
            item["risk_reason"] = "1X2 λ circular — needs rating model"
            item["experimental"] = True
            out.append(item)
    # O/U: evaluate every bookmaker line with the fitted goal distribution.
    # total_ev handles integer pushes and quarter-line half settlements correctly.
    for line, prices in (o.get("odds_ou") or {}).items():
        if "ou" not in active_markets:
            break
        try:
            line_value = float(line)
        except (TypeError, ValueError):
            continue
        over_price, under_price = market_value(prices, 9), market_value(prices, 10)
        market_ou = devig({"over": over_price, "under": under_price})
        for side, pick, odds, market_p in [
            ("over", f"Over {line_value:g}", over_price, market_ou.get("over")),
            ("under", f"Under {line_value:g}", under_price, market_ou.get("under")),
        ]:
            edge = total_ev(line_value, side, odds, lh, la) if odds else -999
            if odds and edge >= min_ev and odds >= min_odds:
                fair_price = total_fair_odds(line_value, side, lh, la)
                probability = 1.0 / fair_price if fair_price > 0 else 0.0
                out.append(pick_entry(
                    o, "ou", pick, probability, odds, edge, market_p,
                    fair_odds_value=fair_price, projection_meta=projection_meta,
                ))
    # BTTS
    btts_market = o.get("odds_btts") or {}
    if isinstance(btts_market, (int, float)):
        btts_market = {"yes": btts_market}
    market_btts = devig({"yes": btts_market.get("yes"), "no": btts_market.get("no")})
    for pick, p, odds, market_p in [
        ("BTTS Yes", pbt, btts_market.get("yes"), market_btts.get("yes")),
        ("BTTS No", 1.0 - pbt, btts_market.get("no"), market_btts.get("no")),
    ]:
        if "btts" not in active_markets:
            continue
        e = ev(p, odds) if odds else -999
        if odds and e >= min_ev and odds >= min_odds:
            out.append(pick_entry(o, "btts", pick, p, odds, e, market_p, projection_meta=projection_meta))
    # AH
    home_ah = {round(float(line), 4): odds for line, odds in (o.get("odds_ah", {}).get("home", []) or [])}
    away_ah = {round(float(line), 4): odds for line, odds in (o.get("odds_ah", {}).get("away", []) or [])}
    for line, c in o.get("odds_ah", {}).get("home", []) or []:
        if "ah" not in active_markets:
            break
        if abs(line) > max_ah_line:
            continue
        # prefer receiving goals — laying big handicap = longshot
        if line < -1.0:
            continue
        e_ah = ah_ev(line, c, lh, la)
        if c >= min_odds and c <= 2.30 and e_ah >= min_ev:
            fair_price = ah_fair_odds(line, "home", lh, la)
            p_approx = 1.0 / fair_price if fair_price > 0 else 0
            counterpart = away_ah.get(round(-float(line), 4))
            market_ah = devig({"home": c, "away": counterpart})
            item = pick_entry(
                o, "ah", f"Home {line:+.2f}", p_approx, c, e_ah, market_ah.get("home"),
                fair_odds_value=fair_price, projection_meta=projection_meta,
            )
            item["experimental"] = True
            out.append(item)
    for line, c in o.get("odds_ah", {}).get("away", []) or []:
        if "ah" not in active_markets:
            break
        if abs(line) > max_ah_line:
            continue
        if line < -1.0:
            continue
        e_ah = ah_ev_away(line, c, lh, la)
        if c >= min_odds and c <= 2.30 and e_ah >= min_ev:
            fair_price = ah_fair_odds(line, "away", lh, la)
            p_approx = 1.0 / fair_price if fair_price > 0 else 0
            counterpart = home_ah.get(round(-float(line), 4))
            market_ah = devig({"away": c, "home": counterpart})
            item = pick_entry(
                o, "ah", f"Away {line:+.2f}", p_approx, c, e_ah, market_ah.get("away"),
                fair_odds_value=fair_price, projection_meta=projection_meta,
            )
            item["experimental"] = True
            out.append(item)
    return out


def select_top_picks(candidates, limit=40, per_market=20, per_match=1,
                     min_ev=0.0, min_edge=0.0, min_odds=1.66, max_odds=None,
                     top_signal_limit=5):
    """Publish full-coverage O/U and AH picks, then mark a diversified Top set.

    Conservative EV absorbs model uncertainty. Fixture and market caps prevent
    a large slate or duplicated alternate lines from flooding the output.
    ``min_edge`` remains in the public signature for API compatibility; Formula
    v4 ranks settlement-aware conservative EV instead of binary probability.
    """
    odds_ceiling = {"ah": 2.30, "ou": 2.30}
    eligible = []
    for pick in candidates:
        market = pick.get("market")
        probability = float(pick.get("probability") or 0)
        odds = float(pick.get("odds") or 0)
        edge = float(pick.get("ev") or 0)
        if market not in odds_ceiling:
            continue
        if pick.get("selection_status") not in {"official", "top_pick"} or pick.get("coverage_status") != "full":
            continue
        eff_odds_cap = max_odds if max_odds is not None else odds_ceiling[market]
        if not min_odds <= odds <= eff_odds_cap:
            continue
        conservative_ev = float(pick.get("conservative_ev", edge - 0.02))
        if conservative_ev < max(float(min_ev), 0.02) or edge > 0.25:
            continue
        price_quality = max(0.0, 1.0 - abs(odds - 1.95) / 0.65)
        score = min(conservative_ev, 0.15) / 0.15 * 80 + price_quality * 20
        item = dict(pick)
        item["rank_score"] = round(score, 2)
        item["locked"] = True
        eligible.append(item)

    eligible.sort(key=lambda p: (p["rank_score"], p["probability"]), reverse=True)
    selected, match_counts, match_markets, market_counts = [], {}, {}, {}
    for pick in eligible:
        match_key = (pick.get("match"), pick.get("start_ts"))
        market = pick["market"]
        if match_counts.get(match_key, 0) >= per_match:
            continue
        if market in match_markets.get(match_key, set()):
            continue
        if market_counts.get(market, 0) >= per_market:
            continue
        selected.append(pick)
        match_counts[match_key] = match_counts.get(match_key, 0) + 1
        match_markets.setdefault(match_key, set()).add(market)
        market_counts[market] = market_counts.get(market, 0) + 1
        if len(selected) >= limit:
            break
    # Top Pick is a small signal inside the broader Official list.  Diversify
    # it so one league cannot occupy the entire strongest-recommendation set.
    league_top_counts = {}
    top_count = 0
    for pick in selected:
        league = pick.get("league") or "Unknown"
        is_top = top_count < top_signal_limit and league_top_counts.get(league, 0) < 2
        pick["is_top_pick"] = is_top
        pick["selection_status"] = "top_pick" if is_top else "official"
        if is_top:
            top_count += 1
            league_top_counts[league] = league_top_counts.get(league, 0) + 1
    return selected


def pick_entry(o, market, pick, p, odds, e, market_probability=None,
               fair_odds_value=None, projection_meta=None):
    b = odds - 1.0
    p_val = p if p is not None else ((e + 1.0) / odds if odds > 0 else 0.0)
    kelly = max(0.0, min((b * p_val - (1.0 - p_val)) / b if b > 0 else 0.0, 0.10)) if p_val else 0.0
    market_p = float(market_probability) if market_probability is not None else None
    projection_meta = projection_meta or {}
    status = projection_candidate_status(projection_meta)
    uncertainty_penalty = 0.02 if status == "official" else (0.04 if status == "shadow" else 1.0)
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
        "conservative_ev": round(e - uncertainty_penalty, 4),
        "uncertainty_penalty": uncertainty_penalty,
        "fair_odds": round(fair_odds_value, 3) if fair_odds_value and fair_odds_value < 100 else None,
        "market_probability": round(market_p, 4) if market_p is not None else None,
        "edge_pct": round(p_val - market_p, 4) if market_p is not None else None,
        "kelly_pct": round(kelly * 100, 2),
        "formula_version": projection_meta.get("formula_version"),
        "lambda_source": projection_meta.get("lambda_source"),
        "coverage_status": projection_meta.get("coverage_status"),
        "data_grade": projection_meta.get("data_grade"),
        "league_model": projection_meta.get("league_model"),
        "selection_status": status,
    }


def backtest_one(r, min_odds=1.66, min_ev=0.0, ledger=None,
                 league_code=None, rating_season=None, strength_weight=None):
    o1, od, o2 = r["odds_home"], r["odds_draw"], r["odds_away"]
    oov, oun = r["odds_over"], r["odds_under"]
    fthg, ftag = r["fthg"], r["ftag"]
    total = fthg + ftag
    margin = fthg - ftag
    market = {
        "home": r.get("home"), "away": r.get("away"), "league": league_code,
        "odds_1x2": {1: o1, 2: od, 3: o2},
        "odds_ou": {2.5: {9: oov, 10: oun}},
        "odds_ah": {
            "home": [(r.get("ah_line"), r.get("ah_home"))] if r.get("ah_line") is not None else [],
            "away": [(-r.get("ah_line"), r.get("ah_away"))] if r.get("ah_line") is not None else [],
        },
        "odds_btts": {},
    }
    projection = build_projection(
        market, rating_season=rating_season,
        strength_weight=strength_weight if league_code else None,
    )
    lh, la = projection["home"], projection["away"]
    if ledger is not None:
        try:
            d = parse_fd_date(r.get("date"))
            ts = d.toordinal() * 86400 + 43200 if d else 0  # noon UTC
            lh, la, _f = apply_rest_adjustment(
                r.get("home"), r.get("away"), ts, lh, la, ledger)
            record_fixtures(ledger, [(r.get("home"), r.get("away"), ts)])
        except Exception:
            pass
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
    candidates = analyze_match(
        market, lh, la, min_odds=min_odds, min_ev=min_ev,
        projection_meta=projection, active_markets=("ou", "ah"),
    )
    official = select_top_picks(
        candidates, limit=1, per_market=1, per_match=1,
        min_ev=min_ev, min_odds=min_odds, top_signal_limit=1,
    )
    from settlement import total_payout
    for candidate in official:
        line = float(candidate["pick"].split()[1])
        if candidate["market"] == "ou":
            side = candidate["pick"].split()[0].lower()
            payout = total_payout(line, side, candidate["odds"], total)
        elif candidate["pick"].startswith("Home"):
            payout = ah_payout(line, candidate["odds"], margin)
        else:
            payout = ah_payout_away(line, candidate["odds"], margin)
        profit = payout - 1.0
        res["picks"].append({
            "market": candidate["market"], "pick": candidate["pick"],
            "odds": candidate["odds"], "ev": candidate["ev"],
            "profit": round(profit, 4),
            "won": True if profit > 0 else (False if profit < 0 else None),
        })
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
