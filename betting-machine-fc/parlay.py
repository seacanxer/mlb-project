"""Deterministic parlay construction from already-qualified FC picks.

The builder never promotes shadow/model-only candidates. AI review, when used
by the API, may only select from these validated candidates.
"""

import hashlib
import json
import math
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_PARLAY_CONFIG = {
    "safe": {
        "label": "Tier 1 Safe",
        "legs": 2,
        "min_probability": 0.58,
        "min_conservative_ev": 0.02,
        "max_leg_odds": 2.05,
        "max_legs_per_league": 1,
    },
    "recommended": {
        "label": "Tier 2 Recommended Pick",
        "legs": 3,
        "min_probability": 0.55,
        "min_conservative_ev": 0.02,
        "max_leg_odds": 2.30,
        "max_legs_per_league": 2,
    },
    "aggressive": {
        "label": "Tier 3 Confidence Aggressive",
        "legs": 4,
        "min_probability": 0.52,
        "min_conservative_ev": 0.02,
        "max_leg_odds": 2.50,
        "max_legs_per_league": 2,
    },
}


def candidate_id(pick: Dict[str, Any]) -> str:
    raw = "|".join(str(pick.get(key) or "") for key in (
        "match_id", "match", "start_ts", "market", "pick", "odds"
    ))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _match_key(pick: Dict[str, Any]) -> str:
    return str(pick.get("match_id") or f"{pick.get('match')}|{pick.get('start_ts')}")


def qualified_candidates(picks: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    qualified = []
    for source in picks:
        if not isinstance(source, dict):
            continue
        if source.get("coverage_status") != "full":
            continue
        if source.get("selection_status") not in {"official", "top_pick"}:
            continue
        if source.get("market") not in {"ou", "ah"}:
            continue
        odds = _number(source.get("odds"))
        probability = _number(source.get("probability"))
        conservative_ev = _number(source.get("conservative_ev"), _number(source.get("ev")) - 0.02)
        if odds <= 1 or not 0 < probability < 1 or conservative_ev < 0.02:
            continue
        item = dict(source)
        item["id"] = candidate_id(item)
        item["odds"] = round(odds, 3)
        item["probability"] = round(probability, 4)
        item["conservative_ev"] = round(conservative_ev, 4)
        qualified.append(item)
    return qualified


def _rank(candidates: List[Dict[str, Any]], tier: str) -> List[Dict[str, Any]]:
    if tier == "safe":
        return sorted(candidates, key=lambda p: (
            _number(p.get("probability")),
            _number(p.get("rank_score")),
            _number(p.get("conservative_ev")),
        ), reverse=True)
    if tier == "recommended":
        return sorted(candidates, key=lambda p: (
            _number(p.get("rank_score")),
            _number(p.get("conservative_ev")),
            _number(p.get("probability")),
        ), reverse=True)
    return sorted(candidates, key=lambda p: (
        _number(p.get("conservative_ev")),
        _number(p.get("odds")),
        _number(p.get("rank_score")),
    ), reverse=True)


def _summarize_slip(
    tier: str,
    spec: Dict[str, Any],
    legs: List[Dict[str, Any]],
    source: str = "framework",
    rationale: Optional[str] = None,
) -> Dict[str, Any]:
    required = int(spec["legs"])
    combined_odds = math.prod(_number(leg.get("odds"), 1.0) for leg in legs)
    model_probability = math.prod(_number(leg.get("probability"), 0.0) for leg in legs)
    return {
        "tier": tier,
        "label": spec["label"],
        "status": "ready" if len(legs) == required else "insufficient_candidates",
        "source": source,
        "required_legs": required,
        "leg_count": len(legs),
        "legs": legs,
        "combined_odds": round(combined_odds, 3) if legs else None,
        "market_implied_probability": round(1.0 / combined_odds, 4) if combined_odds > 1 else None,
        "model_joint_probability": round(model_probability, 4) if legs else None,
        "rationale": rationale or (
            "Framework-ranked independent fixtures using full-coverage official picks."
            if len(legs) == required else
            f"Only {len(legs)} of {required} independent qualified legs are available; no weak leg was forced."
        ),
    }


def build_parlay_slips(
    picks: Iterable[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    candidates = qualified_candidates(picks)
    tier_config = {**DEFAULT_PARLAY_CONFIG, **(config or {})}
    slips = []
    for tier in ("safe", "recommended", "aggressive"):
        spec = {**DEFAULT_PARLAY_CONFIG[tier], **tier_config.get(tier, {})}
        eligible = [candidate for candidate in candidates if (
            _number(candidate.get("probability")) >= _number(spec["min_probability"])
            and _number(candidate.get("conservative_ev")) >= _number(spec["min_conservative_ev"])
            and _number(candidate.get("odds")) <= _number(spec["max_leg_odds"])
        )]
        legs, used_matches, league_counts = [], set(), {}
        for candidate in _rank(eligible, tier):
            match_key = _match_key(candidate)
            league = str(candidate.get("league") or "Unknown")
            if match_key in used_matches or league_counts.get(league, 0) >= int(spec["max_legs_per_league"]):
                continue
            legs.append(candidate)
            used_matches.add(match_key)
            league_counts[league] = league_counts.get(league, 0) + 1
            if len(legs) == int(spec["legs"]):
                break
        slips.append(_summarize_slip(tier, spec, legs))

    fingerprint_payload = [{key: candidate.get(key) for key in ("id", "odds", "probability", "rank_score")} for candidate in candidates]
    fingerprint = hashlib.sha256(json.dumps(fingerprint_payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return {
        "slips": slips,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "fingerprint": fingerprint,
        "methodology": {
            "independent_games_required": True,
            "eligible_markets": ["ou", "ah"],
            "coverage_required": "full",
            "selection_status": ["official", "top_pick"],
            "joint_probability_note": "Product assumes independent legs and is diagnostic, not a guarantee.",
        },
    }


def apply_ai_selection(
    framework: Dict[str, Any],
    selections: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Validate an AI ranking against the deterministic candidate universe."""
    tier_config = {**DEFAULT_PARLAY_CONFIG, **(config or {})}
    by_id = {candidate["id"]: candidate for candidate in framework.get("candidates", [])}
    framework_by_tier = {slip["tier"]: slip for slip in framework.get("slips", [])}
    slips = []
    for tier in ("safe", "recommended", "aggressive"):
        spec = {**DEFAULT_PARLAY_CONFIG[tier], **tier_config.get(tier, {})}
        proposal = selections.get(tier) if isinstance(selections, dict) else None
        ids = proposal.get("leg_ids", []) if isinstance(proposal, dict) else []
        rationale = str(proposal.get("rationale", "")).strip() if isinstance(proposal, dict) else ""
        legs, used_matches, league_counts = [], set(), {}
        for candidate_key in ids:
            candidate = by_id.get(str(candidate_key))
            if not candidate:
                continue
            if (
                _number(candidate.get("probability")) < _number(spec["min_probability"])
                or _number(candidate.get("conservative_ev")) < _number(spec["min_conservative_ev"])
                or _number(candidate.get("odds")) > _number(spec["max_leg_odds"])
            ):
                continue
            match_key = _match_key(candidate)
            league = str(candidate.get("league") or "Unknown")
            if match_key in used_matches or league_counts.get(league, 0) >= int(spec["max_legs_per_league"]):
                continue
            legs.append(candidate)
            used_matches.add(match_key)
            league_counts[league] = league_counts.get(league, 0) + 1
            if len(legs) == int(spec["legs"]):
                break
        if len(legs) == int(spec["legs"]):
            slips.append(_summarize_slip(tier, spec, legs, "ai_reviewed", rationale or "AI ranking validated by framework gates."))
        else:
            fallback = dict(framework_by_tier[tier])
            fallback["rationale"] = f"AI proposal failed validation; framework fallback used. {fallback['rationale']}"
            slips.append(fallback)
    return {**framework, "slips": slips}
