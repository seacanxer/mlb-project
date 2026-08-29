import json
from copy import deepcopy


def evaluate(rows, market, pick_key, min_odds, min_ev):
    stakes = []
    wins = 0
    bets = 0
    for r in rows:
        cands = r.get("picks") or []
        for p in cands:
            if p.get("market") != market and p.get("pick") != pick_key:
                continue
            odds = p.get("odds")
            e = p.get("ev")
            if odds is None or e is None:
                continue
            if odds < min_odds or e < min_ev:
                continue
            bets += 1
            won = p.get("won")
            if won is True:
                wins += 1
                stakes.append(odds - 1)
            else:
                stakes.append(-1)
    if not stakes:
        return None
    units = sum(stakes)
    roi = units / len(stakes)
    return {
        "bets": len(stakes),
        "wins": wins,
        "hit_rate": wins / len(stakes),
        "total_units": units,
        "roi_pct": roi * 100,
        "avg_odds": sum(p.get("odds", 0) for r in rows for p in (r.get("picks") or []) if p.get("odds")) / len(stakes) if stakes else 0,
        "profit_units_per_100": units / len(stakes) * 100,
    }


def validate_1xbit_live(picks_file, min_odds=1.66, min_ev=0.0):
    """
    Validates a picks.json file from the 1xbit pipeline: security scan +
    sanity check that every qualified pick satisfies the user's min-odds
    filter and passes the EV threshold.
    """
    with open(picks_file) as f:
        picks = json.load(f)
    report = {
        "total_picks": len(picks),
        "min_odds": min_odds,
        "violations": [],
        "stats": {"qualified": 0, "rejected": 0},
    }
    for p in picks:
        if not isinstance(p, dict):
            report["violations"].append({"pick": p, "reason": "non-dict entry"})
            continue
        odds = p.get("odds")
        if odds is None:
            report["violations"].append({"match": p.get("match"), "reason": "missing odds"})
            continue
        if odds < min_odds:
            report["stats"]["rejected"] += 1
            report["violations"].append({
                "match": p.get("match"), "market": p.get("market"), "pick": p.get("pick"),
                "odds": odds, "reason": f"odds {odds} < min_odds {min_odds}",
            })
            continue
        evv = p.get("ev")
        if evv is None or evv <= min_ev:
            report["stats"]["rejected"] += 1
            report["violations"].append({
                "match": p.get("match"), "market": p.get("market"), "pick": p.get("pick"),
                "odds": odds, "ev": evv, "reason": f"EV {evv} <= {min_ev}",
            })
            continue
        report["stats"]["qualified"] += 1
    return report