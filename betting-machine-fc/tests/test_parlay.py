from parlay import apply_ai_selection, build_parlay_slips


def pick(i, probability=0.60, odds=1.85, cev=0.05, market="ou"):
    return {
        "match_id": str(i), "match": f"Home {i} vs Away {i}", "start_ts": 1000 + i,
        "league": f"League {i}", "market": market, "pick": "Over 2.5",
        "probability": probability, "odds": odds, "ev": cev + 0.02,
        "conservative_ev": cev, "rank_score": 90 - i,
        "coverage_status": "full", "selection_status": "top_pick" if i < 2 else "official",
    }


def test_builds_three_independent_tiered_slips():
    result = build_parlay_slips([pick(i) for i in range(20)])
    assert [slip["leg_count"] for slip in result["slips"]] == [4, 5, 8]
    assert [slip["min_legs"] for slip in result["slips"]] == [3, 4, 5]
    assert [slip["max_legs"] for slip in result["slips"]] == [4, 5, 8]
    for slip in result["slips"]:
        assert slip["min_legs"] <= slip["leg_count"] <= slip["max_legs"]
        assert slip["status"] == "ready"
        assert len({leg["match_id"] for leg in slip["legs"]}) == slip["leg_count"]
        assert slip["combined_odds"] > 1
    safe_legs = {leg["id"] for leg in result["slips"][0]["legs"]}
    recommended_legs = {leg["id"] for leg in result["slips"][1]["legs"]}
    aggressive_legs = {leg["id"] for leg in result["slips"][2]["legs"]}
    assert safe_legs.isdisjoint(recommended_legs)
    assert safe_legs.isdisjoint(aggressive_legs)
    assert recommended_legs.isdisjoint(aggressive_legs)

def test_tier_leg_ranges_lower_bound():
    result = build_parlay_slips([pick(i) for i in range(3)])
    safe = result["slips"][0]
    assert safe["leg_count"] == 3
    assert safe["status"] == "ready"
    assert all(slip["status"] == "insufficient_candidates" for slip in result["slips"][1:])


def test_never_forces_shadow_or_weak_candidates():
    shadow = pick(1)
    shadow["coverage_status"] = "shadow"
    weak = pick(2, probability=0.40)
    result = build_parlay_slips([shadow, weak])
    assert result["candidate_count"] == 1
    assert all(slip["status"] == "insufficient_candidates" for slip in result["slips"])


def test_invalid_ai_legs_fall_back_to_framework():
    framework = build_parlay_slips([pick(i) for i in range(6)])
    result = apply_ai_selection(framework, {
        "safe": {"leg_ids": ["invented"], "rationale": "bad"},
    })
    assert result["slips"][0]["source"] == "framework"
    assert "failed validation" in result["slips"][0]["rationale"]
