from parlay import apply_ai_selection, build_parlay_slips


def pick(i, probability=0.60, odds=1.85, cev=0.05, market="ou"):
    return {
        "match_id": str(i), "match": f"Home {i} vs Away {i}", "start_ts": 1000 + i,
        "league": f"League {i % 3}", "market": market, "pick": "Over 2.5",
        "probability": probability, "odds": odds, "ev": cev + 0.02,
        "conservative_ev": cev, "rank_score": 90 - i,
        "coverage_status": "full", "selection_status": "top_pick" if i < 2 else "official",
    }


def test_builds_three_independent_tiered_slips():
    result = build_parlay_slips([pick(i) for i in range(6)])
    assert [slip["leg_count"] for slip in result["slips"]] == [2, 3, 4]
    assert all(slip["status"] == "ready" for slip in result["slips"])
    for slip in result["slips"]:
        assert len({leg["match_id"] for leg in slip["legs"]}) == slip["leg_count"]
        assert slip["combined_odds"] > 1


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
