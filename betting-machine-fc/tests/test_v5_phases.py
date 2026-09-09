import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import strength_rating as sr
from main import default_gate_context, gate_reason, select_top_picks
from prediction import build_projection_ou_only, project_match


def _shadow(prob=0.62, odds=1.9, cons=0.08, edge=0.06, **kw):
    d = {"match": "X vs Y", "start_ts": 1, "market": "ou", "pick": "Over 2.5",
         "probability": prob, "odds": odds, "ev": 0.12,
         "market_probability": prob - edge, "edge_pct": edge,
         "conservative_ev": cons, "coverage_status": "shadow",
         "selection_status": "shadow", "has_both_markets": True}
    d.update(kw)
    return d


def test_gate_reason_names_first_rejection():
    ctx = default_gate_context()
    ctx["include_shadow"] = True
    assert gate_reason(_shadow(), ctx) == ""
    bad_odds = _shadow(odds=99.0)
    assert gate_reason(bad_odds, ctx) == "odds_range"
    bad_prob = _shadow(prob=0.40)
    assert gate_reason(bad_prob, ctx) == "breakeven"
    bad_edge = _shadow(edge=0.001)
    assert gate_reason(bad_edge, ctx) == "edge"
    bad_one = dict(_shadow(), market="1x2")
    assert gate_reason(bad_one, ctx) == ""
    weak_one = dict(_shadow(), market="1x2", probability=0.40)
    assert gate_reason(weak_one, ctx) == "1x2_strict"


def test_watch_route_and_edge():
    from league_profiles import get_league_profile
    prof = get_league_profile("Norway. Division 2")
    assert prof.route == "watch"
    assert prof.key == "UNVALIDATED"
    watch = _shadow(prob=0.62, odds=1.9, cons=0.08, edge=0.03,
                    league_model="UNVALIDATED")
    assert select_top_picks([watch], min_odds=1.5, include_shadow=True) == []
    watch_ok = _shadow(prob=0.62, odds=1.9, cons=0.08, edge=0.06,
                       league_model="UNVALIDATED")
    assert len(select_top_picks([watch_ok], min_odds=1.5, include_shadow=True)) == 1


def test_category_tokens_require_exact_match():
    teams = {"Tromso": {"att": 1.1, "def": 0.9}, "Tromso II": {"att": 0.8, "def": 1.2}}
    assert sr.match_team("Tromso II", teams) == "Tromso II"
    assert sr.match_team("Tromso", teams) == "Tromso"
    # reserve side must not fuzzy-merge into the senior side
    teams_senior = {"Tromso": {"att": 1.1, "def": 0.9}}
    assert sr.match_team("Tromso II", teams_senior) is None
    # junior suffix is no longer stripped as junk
    assert sr.normalize_team_name("Tromso II") == "tromso ii"


def test_alias_provenance_table_exists():
    assert sr._ALIAS_SOURCE.get("man city") == "verified:football-data"
    assert sr.match_team("Man City", {"Manchester City": {"att": 1, "def": 1}}) == "Manchester City"


def test_diagnose_match_coverage_categories(tmp_path, monkeypatch):
    csv = tmp_path / "E0_2425.csv"
    csv.write_text("Date,HomeTeam,AwayTeam,FTHG,FTAG\n" + "\n".join(
        f"{i:02d}/01/2025,Alpha,Beta,2,1" for i in range(1, 21)))
    monkeypatch.setattr(sr.sh, "download", lambda *a, **k: str(csv))
    monkeypatch.setattr(sr, "DATA_DIR", str(tmp_path))
    sr._mem_cache.clear()
    sr._no_coverage.clear()
    assert sr.diagnose_match_coverage("Alpha", "Beta", "E0", season="2425") == "ok-full"
    assert sr.diagnose_match_coverage("Gamma", "Beta", "E0", season="2425").startswith("team-miss:home")
    assert sr.diagnose_match_coverage("Alpha", "Gamma", "E0", season="2425").startswith("team-miss:away")
    assert sr.diagnose_match_coverage("A", "B", "Atlantis. Premier") == "no-league-code"
    # cross-league history is still full coverage (provenance tracked):
    # PromotedFC missing from E1 file but present in E0 sibling file.
    import time as _t
    now = _t.time()
    def fake_load(code, season):
        if code == "E1":
            return {"teams": {"Local": {"att": 1.0, "def": 1.0}},
                    "league_avg": 1.3, "home_adv": 1.2, "built_at": now}
        if code == "E0":
            return {"teams": {"PromotedFC": {"att": 1.3, "def": 0.9}},
                    "league_avg": 1.4, "home_adv": 1.1, "built_at": now}
        return None
    monkeypatch.setattr(sr, "load_ratings", fake_load)
    got = sr.diagnose_match_coverage("PromotedFC", "Local", "England. Championship")
    assert got.startswith("ok-full:cross"), got
    lh, la = sr.strength_lams("PromotedFC", "Local", "England. Championship",
                              season="2425")
    assert lh > la > 0
    sr._no_coverage.clear()


def test_coverage_misses_endpoint():
    from fastapi.testclient import TestClient
    import server
    res = TestClient(server.app).get("/api/coverage-misses")
    assert res.status_code == 200
    data = res.json()
    assert "misses" in data and "coverage_reasons" in data


def test_no_coverage_ttl_and_retry():
    sr._no_coverage.clear()
    sr._remember_no_coverage("E0", "9999")
    assert sr._coverage_blocked("E0", "9999") is True
    # force expiry by backdating
    import time as _t
    sr._no_coverage[("E0", "9999")] = _t.time() - sr.RATINGS_TTL_S - 1
    assert sr._coverage_blocked("E0", "9999") is False
    sr._no_coverage.clear()


def test_ou_only_partial_projection_and_gate():
    m = {"home": "A", "away": "B", "league": "USA. MLS",
         "odds_1x2": {}, "odds_ou": {2.5: {9: 2.2, 10: 1.72}}, "odds_ah": {}}
    proj = build_projection_ou_only(m)
    assert proj["coverage_status"] == "shadow"
    assert proj["split_assumed"] is True
    assert proj["lambda_source"] == "market-partial-ou"
    proj2, path = project_match(m)
    assert path == "ou_only"
    assert proj2["coverage_status"] == "shadow"
    # blocked leagues stay blocked through every tier
    bad = dict(m, league="Club Friendlies")
    try:
        project_match(bad)
        assert False, "must raise"
    except ValueError:
        pass


def test_partial_ou_candidate_skips_both_markets_gate():
    from main import analyze_match
    m = {"home": "A", "away": "B", "league": "USA. MLS", "match_id": 1,
         "start_ts": 9999999999,
         "odds_1x2": {}, "odds_ou": {2.5: {9: 2.6, 10: 1.72}}, "odds_ah": {}}
    proj, _ = project_match(m)
    cands = analyze_match(m, proj["home"], proj["away"], min_odds=1.5, min_ev=0.0,
                          projection_meta=proj, active_markets=("ou", "ah"))
    assert cands, "OU-only must still produce OU candidates"
    assert all(c["market"] == "ou" for c in cands)
    assert all(c.get("partial_ou") for c in cands)


def test_calibration_fit_apply_identity_fallback():
    from calibration import apply_platt, fit_platt
    pairs = [(0.6 + 0.01 * (i % 5), 1 if i % 2 == 0 else 0) for i in range(120)]
    a, b = fit_platt(pairs)
    assert b >= 0
    q = apply_platt(0.65, {"a": a, "b": b})
    assert 0 < q < 1
    assert apply_platt(0.65, None) is None
    assert apply_platt(0.65, {}) is None


def test_prediction_card_follows_league_rho():
    from match_prediction import compute_prediction_card
    import time as _t
    base = {"lambdas": {"home": 1.5, "away": 1.2},
            "info": {"home": "A", "away": "B", "league": "L",
                     "start_ts": _t.time() + 3600, "match_id": "1"},
            "model": {"coverage_status": "full", "formula_version": "ou-ah-v4.2.0",
                      "lambda_source": "market+strength", "rho": -0.04}}
    auto = compute_prediction_card(base)
    assert auto["parameters"]["rho"] == -0.04
    assert auto["model_meta"]["scenario_only"] is False
    manual = compute_prediction_card(base, rho=-0.13)
    assert manual["parameters"]["rho"] == -0.13
    assert manual["model_meta"]["scenario_only"] is True
    assert auto["score_matrix"] != manual["score_matrix"]


def test_decision_mapping_explicit():
    picks = select_top_picks([_shadow()], min_odds=1.5, include_shadow=True)
    assert picks and picks[0]["decision"] == "watch"
    official = dict(_shadow(), coverage_status="full", selection_status="official",
                    policy_version="quality-v1", lambda_source="market+strength")
    picks = select_top_picks([official], min_odds=1.5)
    assert picks and picks[0]["decision"] in {"official", "top_pick"}
