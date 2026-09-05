import os
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app, classify_settlement_status

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "scan_state" in data
    assert "diagnostics" in data["scan_state"]


def test_picks_endpoint():
    response = client.get("/api/picks?min_odds=1.66&min_ev=0.0")
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "picks" in data
    assert data["summary"]["min_odds_floor"] == 1.66
    assert data["summary"]["max_picks_per_match"] == 1
    assert "top_pick_count" in data["summary"]
    for pick in data["picks"]:
        assert pick["odds"] >= 1.66
        assert pick["ev"] >= 0.0
        assert pick["locked"] is True
        assert "kelly_stake" not in pick

    assert len(data["picks"]) <= data["summary"]["selection_limit"]


def test_tracker_endpoint():
    response = client.get("/api/tracker")
    assert response.status_code == 200
    data = response.json()
    assert data["unit_size"] == 1.0
    assert "roi_pct" in data["summary"]
    assert "duplicates_hidden" in data["summary"]
    assert "market_performance" in data
    assert "last_successful_scan_time" in data
    buckets = ["locked", "live", "overdue", "settled"]
    assert set(data["status_counts"]) == set(buckets)
    all_bets = [bet for status in buckets for bet in data[status]]
    assert all(bet["settlement_status"] in buckets for bet in all_bets)
    assert all("timing_status" in bet for bet in all_bets)
    assert all("home_score" in bet and "away_score" in bet for bet in all_bets)
    assert data["summary"]["pending_picks"] == sum(data["status_counts"][status] for status in ("locked", "live", "overdue"))


def test_settlement_status_buckets_follow_kickoff_clock():
    now = 1_000_000
    assert classify_settlement_status({"settled": 1, "start_ts": now - 10_000}, now) == "settled"
    assert classify_settlement_status({"settled": 0, "start_ts": now + 60}, now) == "locked"
    assert classify_settlement_status({"settled": 0, "start_ts": now - 60}, now) == "live"
    assert classify_settlement_status({"settled": 0, "start_ts": now - 6_301}, now) == "overdue"
    assert classify_settlement_status({"settled": 0, "start_ts": None}, now) == "locked"


def test_picks_odds_floor_enforcement():
    # Attempting to query with min_odds=1.20 should still enforce min 1.66 floor
    response = client.get("/api/picks?min_odds=1.20")
    assert response.status_code == 200
    data = response.json()
    for pick in data["picks"]:
        assert pick["odds"] >= 1.66


def test_config_endpoints():
    res_get = client.get("/api/config")
    assert res_get.status_code == 200
    cfg = res_get.json()
    assert "filters" in cfg

    # Test updating config with odds below 1.66 - should auto-clamp to 1.66
    cfg["filters"]["min_odds"] = 1.40
    res_post = client.post("/api/config", json=cfg)
    assert res_post.status_code == 200
    saved_cfg = res_post.json()["config"]
    assert saved_cfg["filters"]["min_odds"] >= 1.66
    assert saved_cfg["filters"]["top_picks_per_match"] == 1
    assert saved_cfg["scan_match_limit"] == 500


def test_simulation_endpoint():
    payload = {
        "bankroll": 1000.0,
        "stake_pct": 0.02,
        "odds": 1.95,
        "probability": 0.58,
        "rounds": 50,
        "iterations": 100,
        "strategy": "flat",
    }
    response = client.post("/api/simulate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "median" in data
    assert "p5_worst" in data
    assert "p95_best" in data
    assert "ruin_pct" in data
    assert len(data["sample_trajectories"]) > 0


if __name__ == "__main__":
    pytest.main(["-v", __file__])
