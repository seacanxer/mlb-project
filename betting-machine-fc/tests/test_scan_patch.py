import time

import pytest

from main import analyze_match, select_top_picks
from prediction import build_projection_fallback


def market():
    return {
        "home": "A", "away": "B", "league": "USA. MLS", "start_ts": time.time() + 3600,
        "odds_1x2": {}, "odds_ou": {2.5: {9: 1.95, 10: 1.95}},
        "odds_ah": {"home": [(-0.5, 1.95)], "away": [(0.5, 1.95)]},
    }


def candidate(**overrides):
    result = {
        "match": "A vs B", "start_ts": time.time() + 3600, "league": "USA. MLS",
        "market": "ou", "pick": "Over 2.5", "odds": 2.0, "probability": 0.55,
        "ev": 0.08, "conservative_ev": 0.04, "coverage_status": "shadow",
        "selection_status": "shadow", "has_both_markets": True,
        "policy_version": "quality-v1", "lambda_source": "market+strength", "market_probability": .5,
    }
    result.update(overrides)
    return result


def test_fallback_missing_1x2_is_shadow_and_can_be_analyzed():
    quote = market()
    projection = build_projection_fallback(quote)
    assert projection["coverage_status"] == "shadow"
    assert projection["home"] > projection["away"] > 0
    assert sum(projection["fair_1x2"]) == pytest.approx(1)
    analyze_match(quote, projection["home"], projection["away"], projection_meta=projection)


@pytest.mark.parametrize("field", ["odds_ou", "odds_ah"])
def test_fallback_requires_both_paired_markets(field):
    quote = market()
    quote[field] = {}
    with pytest.raises(ValueError):
        build_projection_fallback(quote)


@pytest.mark.parametrize("league", ["Club Friendlies", "Italy. Primavera", "UEFA Champions League. Team vs Player"])
def test_fallback_never_bypasses_blocked_competition(league):
    quote = market()
    quote["league"] = league
    with pytest.raises(ValueError):
        build_projection_fallback(quote)


def test_shadow_reduced_gate_never_takes_official_top_slot():
    shadow = candidate(conservative_ev=0.08)
    official = candidate(match="C vs D", coverage_status="full", selection_status="official")
    selected = select_top_picks([shadow, official], top_signal_limit=1, include_shadow=True)
    assert len(selected) == 2
    assert selected[0]["selection_status"] == "shadow"
    assert not selected[0]["is_top_pick"]
    assert selected[1]["is_top_pick"]
    assert not selected[0]["locked"]


@pytest.mark.parametrize("changes", [{"has_both_markets": False}, {"odds": 2.6}, {"conservative_ev": -0.01}])
def test_shadow_noise_gates(changes):
    assert select_top_picks([candidate(**changes)], max_odds=2.75) == []


def test_official_wider_price_cap_and_idempotent_reselection():
    pick = candidate(coverage_status="full", selection_status="official", odds=2.7)
    first = select_top_picks([pick], max_odds=2.75)
    assert len(first) == 1
    assert select_top_picks(first, max_odds=2.75) == first


def test_api_does_not_resurrect_rejected_or_started_candidates(monkeypatch):
    import server
    from fastapi.testclient import TestClient
    saved = candidate(locked=True, coverage_status="full", selection_status="official")
    expired = candidate(match="Old", start_ts=time.time() - 60)
    rejected = candidate(conservative_ev=-0.1)
    monkeypatch.setattr(server, "load_config", lambda: {"filters": {"top_pick_limit": 50}})
    monkeypatch.setattr(server, "load_picks_file", lambda: [saved, expired])
    monkeypatch.setattr(server, "load_detailed_matches", lambda: [{"picks": [rejected]}])
    result = TestClient(server.app).get("/api/picks").json()
    assert len(result["picks"]) == 1
    assert result["summary"]["top_pick_count"] == 1
    assert result["picks"][0]["locked"] is True


def test_scanner_recovers_missing_1x2_and_records_diagnostics(tmp_path, monkeypatch):
    import server
    import fatigue
    quote = market()
    monkeypatch.setattr(server, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "load_config", lambda: {"data_source": "1xbit", "scan_window_hours": 24})
    saved = {}
    monkeypatch.setattr(server, "save_config", lambda cfg: saved.update(cfg))
    monkeypatch.setattr(server.sc, "list_matches_paginated", lambda **kw: [{"I": 1, "L": "USA. MLS"}, {"I": 2, "L": "Club Friendlies"}])
    monkeypatch.setattr(server.sc, "get_match", lambda match_id: quote)
    monkeypatch.setattr(server.sc, "extract_markets", lambda value: value)
    monkeypatch.setattr(server.db, "insert_bet", lambda pick: (1, True))
    monkeypatch.setattr(fatigue, "load_ledger", lambda: {})
    monkeypatch.setattr(fatigue, "save_ledger", lambda ledger: None)
    monkeypatch.setattr(server, "scan_state", dict(server.scan_state))
    server.execute_live_scan_sync()
    assert server.scan_state["error"] is None
    diag = saved["last_scan_diagnostics"]
    assert diag["discovered"] == 2
    assert diag["blocked_leagues"] == 1
    assert diag["fallback"] == diag["processed"] == 1
    assert diag["full"] == 0
