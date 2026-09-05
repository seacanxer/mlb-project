import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from league_profiles import get_league_profile
from main import select_top_picks
from model import fit_margin_from_ah, fit_total_from_ou, total_ev
from prediction import build_projection, projection_candidate_status, select_main_ou


def test_main_ou_accepts_json_string_outcome_keys():
    market = {
        "2.25": {"9": 1.70, "10": 2.20},
        "2.5": {"9": 1.94, "10": 1.96},
    }
    assert select_main_ou(market) == (2.5, 1.94, 1.96)


def test_quarter_total_fit_balances_settlement_returns():
    total, _ = fit_total_from_ou(1.91, 1.99, 2.25)
    over_return = total_ev(2.25, "over", 1.91, total / 2, total / 2) + 1
    under_return = total_ev(2.25, "under", 1.99, total / 2, total / 2) + 1
    # The probability matrix deliberately caches lambdas at 0.001 precision.
    assert abs(over_return - under_return) < 2e-4


def test_ah_fit_uses_paired_prices_for_margin_direction():
    margin, _ = fit_margin_from_ah(2.7, -0.5, 1.80, 0.5, 2.10)
    assert margin > 0


def test_shadow_league_is_visible_but_never_official():
    market = {
        "home": "A",
        "away": "B",
        "league": "Norway. Eliteserien",
        "odds_1x2": {"1": 2.20, "2": 3.40, "3": 3.10},
        "odds_ou": {"3.0": {"9": 1.95, "10": 1.95}},
        "odds_ah": {"home": [[-0.25, 1.95]], "away": [[0.25, 1.95]]},
    }
    projection = build_projection(market)
    assert projection["coverage_status"] == "shadow"
    assert projection["lambda_source"] == "market+league-prior"
    assert projection_candidate_status(projection) == "shadow"


def test_unvalidated_lower_tier_is_blocked():
    profile = get_league_profile("Germany. Regionalliga West")
    assert profile.route == "blocked"


def test_cached_top_pick_survives_api_reselection():
    candidate = {
        "match": "A vs B",
        "start_ts": 1,
        "league": "Spain. La Liga",
        "market": "ou",
        "pick": "Over 2.5",
        "probability": 0.57,
        "odds": 1.90,
        "ev": 0.083,
        "conservative_ev": 0.063,
        "coverage_status": "full",
        "selection_status": "top_pick",
    }
    selected = select_top_picks([candidate])
    assert len(selected) == 1
    assert selected[0]["is_top_pick"] is True
