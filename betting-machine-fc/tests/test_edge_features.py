import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date

import fatigue
import strength_rating as sr
from fatigue import apply_rest_adjustment, record_fixtures, rest_factor
from main import backtest_one, select_top_picks
from model import lam_from_1x2


def test_parse_fd_date():
    assert sr.parse_fd_date("15/08/2025") == date(2025, 8, 15)
    assert sr.parse_fd_date("2025-08-15") == date(2025, 8, 15)
    assert sr.parse_fd_date("bogus") is None
    assert sr.parse_fd_date(None) is None


def _synth_rows():
    # Connected 4-team mini league (home+away round robin).
    # S=strong, M1/M2=mid, W=weak. def HIGH = concedes more (worse).
    fx = [("S", "W", 3, 0), ("W", "S", 0, 2),
          ("S", "M1", 2, 0), ("M1", "S", 1, 1),
          ("S", "M2", 2, 0), ("M2", "S", 1, 1),
          ("M1", "M2", 1, 1), ("M2", "M1", 1, 1),
          ("M1", "W", 2, 0), ("W", "M1", 0, 1),
          ("M2", "W", 2, 0), ("W", "M2", 0, 1)]
    return [{"date": f"{i + 1:02d}/01/2025", "home": h, "away": a,
             "fthg": gh, "ftag": ga} for i, (h, a, gh, ga) in enumerate(fx)]


def test_mle_rating_orders_teams():
    teams, avg, hadv = sr.mle_rating(_synth_rows())
    assert teams["S"]["att"] > 1.0 > teams["W"]["att"]
    assert teams["W"]["def"] > 1.0 > teams["S"]["def"]
    assert 0.5 < avg < 2.5
    assert hadv > 1.0
    # final output stays inside documented clamp bounds
    for t in teams.values():
        assert 0.6 <= t["att"] <= 1.8 and 0.6 <= t["def"] <= 1.8


def test_mle_empty():
    teams, avg, hadv = sr.mle_rating([])
    assert teams == {}


def test_resolve_code():
    assert sr.resolve_code("E0") == "E0"
    assert sr.resolve_code("England. Premier League") == "E0"
    assert sr.resolve_code("Norway. Division 2") is None
    assert sr.resolve_code(None) is None


def test_match_team():
    teams = {"Manchester City": {"att": 1.2, "def": 0.9}}
    assert sr.match_team("Manchester City", teams) == "Manchester City"
    assert sr.match_team("Manchester City FC", teams) == "Manchester City"
    assert sr.match_team("Liverpool", teams) is None


def test_hybrid_fallback_unknown_league():
    lh, la, src = sr.hybrid_lams("A", "B", "Norway. Division 2", 1.5, 1.2)
    assert (lh, la) == (1.5, 1.2) and src == "market-only"


def test_hybrid_blend_with_ratings(tmp_path, monkeypatch):
    csv = tmp_path / "E0_2425.csv"
    csv.write_text("Date,HomeTeam,AwayTeam,FTHG,FTAG\n" + "\n".join(
        f"{i:02d}/01/2025,StrongHome,WeakAway,3,0" for i in range(1, 21)))
    monkeypatch.setattr(sr.sh, "download", lambda *a, **k: str(csv))
    monkeypatch.setattr(sr, "DATA_DIR", str(tmp_path))
    sr._mem_cache.clear()
    lh, la, src = sr.hybrid_lams("StrongHome", "WeakAway", "E0", 1.4, 1.3,
                                 weight=0.5, season="2425")
    assert src == "market+strength"
    assert lh > 1.4 and la < 1.3  # strength pulls toward 3-0 home rout


def test_rest_factor_tiers():
    assert rest_factor(None) == 1.0
    assert rest_factor(9) == 1.0
    assert rest_factor(4) == 0.99
    assert rest_factor(2.5) == 0.97
    assert rest_factor(1) == 0.94


def test_rest_no_history_unchanged():
    lh, la, info = apply_rest_adjustment("A", "B", 1_000_000, 1.5, 1.2, {})
    assert (lh, la) == (1.5, 1.2) and info["home_rest_d"] is None


def test_rest_short_rest_shrinks():
    ledger = {}
    record_fixtures(ledger, [("A", "C", 1_000_000)])
    lh, la, info = apply_rest_adjustment("A", "B", 1_000_000 + 1 * 86400, 1.5, 1.2, ledger)
    assert info["home_rest_d"] == 1.0
    assert lh < 1.5 and la > 1.2  # tired attack down, tired defence concedes


def test_ledger_trims_and_roundtrips(tmp_path):
    p = str(tmp_path / "ledger.json")
    lg = {}
    record_fixtures(lg, [("A", "B", i) for i in range(30)])
    assert len(lg["a"]) == fatigue.MAX_KEPT
    fatigue.save_ledger(lg, path=p)
    back = fatigue.load_ledger(path=p)
    assert back["a"] == sorted(lg["a"])[-fatigue.MAX_KEPT:]


def test_backtest_uses_1x2_fitter():
    r = {"date": "15/08/2025", "home": "H", "away": "A", "fthg": 2, "ftag": 1,
         "odds_home": 2.0, "odds_draw": 3.4, "odds_away": 3.8,
         "odds_over": 2.1, "odds_under": 1.8}
    res = backtest_one(r, min_odds=1.0, min_ev=-9)
    lh, la, _ = lam_from_1x2(2.0, 3.4, 3.8)
    assert abs(res["lambdas"]["home"] - round(lh, 3)) < 1e-9
    assert abs(res["lambdas"]["away"] - round(la, 3)) < 1e-9


def _cand(market, prob, odds, ev_val, edge, indep=True):
    return {"match": "X vs Y", "start_ts": 1, "market": market, "pick": "P",
            "probability": prob, "odds": odds, "ev": ev_val,
            "market_probability": prob - edge, "edge_pct": edge,
            "independent_signal": indep}


def test_gates_ou_floor_058():
    cands = [_cand("ou", 0.55, 1.9, 0.10, 0.05), _cand("ou", 0.59, 1.9, 0.10, 0.05)]
    picks = select_top_picks(cands, min_ev=0.0, min_edge=0.02, min_odds=1.6)
    assert len(picks) == 1 and picks[0]["probability"] == 0.59


def test_gates_1x2_circular_strict():
    weak = _cand("1x2", 0.45, 2.0, 0.06, 0.05, indep=False)
    strong = _cand("1x2", 0.50, 2.0, 0.08, 0.05, indep=False)
    picks = select_top_picks([weak, strong], min_ev=0.0, min_edge=0.02, min_odds=1.6)
    assert [p["probability"] for p in picks] == [0.50]
