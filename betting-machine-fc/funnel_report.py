"""Rejection funnel + single-gate ablation over a stored scan snapshot.

For every candidate: first failing gate (coverage first, price last).
Then relax ONE gate at a time and report the pick-count delta, so a
loosening decision names its exact volume source. Research-only.

    python funnel_report.py [--detailed matches_detailed.json]
"""
import argparse
import json
import os
import sys
from collections import Counter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from main import analyze_match, default_gate_context, gate_reason, select_top_picks
from prediction import build_projection, build_projection_fallback

ABLATIONS = {
    "no_coverage_gate": {"include_shadow": True, "_allow_all_coverage": True},
    "no_odds_floor": {"min_odds": 1.01},
    "no_odds_cap": {"max_odds": 99.0},
    "no_cons_ev": {"min_ev": -99.0, "shadow_min_cons_ev": -99.0, "cons_ev_base": -99.0},
    "no_breakeven": {"shadow_prob_margin": -1.0},
    "no_edge": {"min_edge_official": -99.0, "min_edge_shadow": -99.0,
                "min_edge_watch": -99.0, "min_edge": -99.0},
    "no_both_markets": {"_skip_both_markets": True},
}


def select_with(cands, base, **kw):
    import main as _main
    ctx = default_gate_context()
    ctx.update({k: v for k, v in base.items()})
    ctx.update(kw)
    allow_all = ctx.pop("_allow_all_coverage", False)
    skip_both = ctx.pop("_skip_both_markets", False)
    orig_gate = _main.gate_reason

    def patched(pick, c):
        if allow_all:
            pick = dict(pick)
            if pick.get("coverage_status") == "shadow":
                pick["selection_status"] = "shadow"
            elif pick.get("coverage_status") == "full":
                pick["selection_status"] = "official"
            else:
                return "coverage"
        if skip_both and pick.get("coverage_status") == "shadow":
            pick = dict(pick, has_both_markets=True)
        return orig_gate(pick, c)

    _main.gate_reason = patched
    try:
        return select_top_picks(
            cands, limit=500, per_market=500, per_match=5, min_ev=ctx["min_ev"],
            min_edge=ctx["min_edge"], min_odds=ctx["min_odds"],
            max_odds=ctx["max_odds"], top_signal_limit=500,
            include_shadow=ctx["include_shadow"],
            shadow_min_cons_ev=ctx["shadow_min_cons_ev"],
            shadow_prob_margin=ctx["shadow_prob_margin"],
            min_edge_official=ctx["min_edge_official"],
            min_edge_shadow=ctx["min_edge_shadow"],
            min_edge_watch=ctx["min_edge_watch"],
            cons_ev_base=ctx["cons_ev_base"])
    finally:
        _main.gate_reason = orig_gate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--detailed", default=os.path.join(BASE_DIR, "matches_detailed.json"))
    args = ap.parse_args()
    det = json.load(open(args.detailed, encoding="utf-8"))
    cands, coverages = [], Counter()
    for d in det:
        o = d.get("info") or {}
        try:
            proj = build_projection(o)
        except Exception as exc:
            try:
                proj = build_projection_fallback(o, reason=exc)
            except Exception:
                coverages["error"] += 1
                continue
        coverages[proj.get("coverage_status", "?")] += 1
        try:
            cands.extend(analyze_match(
                o, proj["home"], proj["away"], min_odds=1.50, min_ev=0.0,
                projection_meta=proj, active_markets=("ou", "ah", "1x2")))
        except Exception:
            continue
    print(f"matches={len(det)} coverage={dict(coverages)} candidates={len(cands)}")
    base = {"include_shadow": True}
    ctx0 = default_gate_context()
    ctx0.update(base)
    hist = Counter(gate_reason(c, ctx0) or "passed" for c in cands)
    print("first-rejection:", dict(hist))
    base_n = len(select_with(cands, base))
    print(f"baseline selected={base_n}")
    print(f"{'ablation':>18} {'n':>5} {'delta':>6}")
    for name, kw in ABLATIONS.items():
        n = len(select_with(cands, base, **kw))
        print(f"{name:>18} {n:>5} {n - base_n:>+6}")
    # shadow-only view: which shadow picks survive strictness
    sh = [c for c in cands if c.get("coverage_status") == "shadow"]
    sh_sel = [p for p in select_with(cands, base) if p.get("coverage_status") == "shadow"]
    print(f"shadow candidates={len(sh)} shadow selected={len(sh_sel)}")


if __name__ == "__main__":
    main()
