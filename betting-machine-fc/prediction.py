"""Shared live/backtest projection path for Formula v4."""
import math
from model import (
    ah_ev,
    ah_ev_away,
    fit_margin_from_ah,
    fit_total_from_ou,
    lam_from_1x2,
)
from league_profiles import get_league_profile
from strength_rating import get_league_rho, hybrid_lams, resolve_season
from model import RHO_DEFAULT


FORMULA_VERSION = "ou-ah-v4.3.0"


def _valid_price(value):
    try:
        return value is not None and math.isfinite(float(value)) and float(value) > 1.0
    except (TypeError, ValueError):
        return False


def _market_value(mapping, key):
    if not isinstance(mapping, dict):
        return None
    return mapping.get(key, mapping.get(str(key)))


def select_main_ou(odds_ou):
    """Choose the most balanced complete O/U line as the reference main line."""
    candidates = []
    for raw_line, prices in (odds_ou or {}).items():
        try:
            line = float(raw_line)
            over, under = float(_market_value(prices, 9)), float(_market_value(prices, 10))
        except (TypeError, ValueError, AttributeError):
            continue
        if not (_valid_price(over) and _valid_price(under)):
            continue
        balance = abs((1.0 / over) - (1.0 / under))
        candidates.append((balance, abs(line - 2.5), line, over, under))
    if not candidates:
        return None
    _, _, line, over, under = min(candidates)
    return line, over, under


def select_main_ah(odds_ah):
    """Return a paired home/away AH line whose prices are closest to balanced."""
    home = {}
    away = {}
    for line, price in ((odds_ah or {}).get("home") or []):
        try:
            if _valid_price(price):
                home[round(float(line), 4)] = float(price)
        except (TypeError, ValueError):
            continue
    for line, price in ((odds_ah or {}).get("away") or []):
        try:
            if _valid_price(price):
                away[round(float(line), 4)] = float(price)
        except (TypeError, ValueError):
            continue
    candidates = []
    for home_line, home_odds in home.items():
        away_line = round(-home_line, 4)
        away_odds = away.get(away_line)
        if away_odds is None:
            continue
        balance = abs((1.0 / home_odds) - (1.0 / away_odds))
        candidates.append((balance, abs(home_line), home_line, home_odds, away_line, away_odds))
    if not candidates:
        return None
    _, _, home_line, home_odds, away_line, away_odds = min(candidates)
    return home_line, home_odds, away_line, away_odds


def build_projection(market, *, rating_season=None, strength_weight=None):
    """Build coherent O/U + AH lambdas and attach honest coverage metadata."""
    odds_1x2 = market.get("odds_1x2") or {}
    if not all(_valid_price(_market_value(odds_1x2, key)) for key in (1, 2, 3)):
        raise ValueError("complete 1X2 prices are required to identify score direction")
    main_ou = select_main_ou(market.get("odds_ou"))
    if main_ou is None:
        raise ValueError("complete two-sided O/U market is required")

    o1, od, o2 = (float(_market_value(odds_1x2, key)) for key in (1, 2, 3))
    base_lh, base_la, fair_1x2 = lam_from_1x2(o1, od, o2)
    line, over_odds, under_odds = main_ou
    market_total, fair_over = fit_total_from_ou(over_odds, under_odds, line)

    base_total = max(0.1, base_lh + base_la)
    market_margin = (base_lh - base_la) * market_total / base_total
    margin_source = "1x2"
    main_ah = select_main_ah(market.get("odds_ah"))
    if main_ah is not None:
        home_line, home_odds, away_line, away_odds = main_ah
        market_margin, _ = fit_margin_from_ah(
            market_total, home_line, home_odds, away_line, away_odds,
            prior_margin=market_margin,
        )
        margin_source = "ah"

    bound = max(0.0, market_total - 0.20)
    market_margin = min(bound, max(-bound, market_margin))
    market_lh = max(0.10, (market_total + market_margin) / 2.0)
    market_la = max(0.10, (market_total - market_margin) / 2.0)

    profile = get_league_profile(market.get("league"))
    source = "market-only"
    coverage = profile.route
    data_grade = profile.data_grade
    history_weight = 0.0
    rho = RHO_DEFAULT
    total_disagreement = None  # |history-blended total - market total|
    ratings_files = {"home": None, "away": None}

    if profile.route == "rated":
        weight = profile.prior_weight if strength_weight is None else float(strength_weight)
        lh, la, source = hybrid_lams(
            market.get("home"), market.get("away"), market.get("league"),
            market_lh, market_la, weight=weight, season=rating_season,
        )
        history_weight = weight if source == "market+strength" else 0.0
        coverage = "full" if source == "market+strength" else "market_only"
        if coverage == "full":
            try:
                from strength_rating import rating_file_for
                # Same season hybrid_lams used (explicit override or resolved),
                # so provenance labels match the blended ratings.
                _season = rating_season or resolve_season(profile.key)
                ratings_files = {
                    "home": rating_file_for(market.get("home"), market.get("league"), season=_season),
                    "away": rating_file_for(market.get("away"), market.get("league"), season=_season),
                }
            except Exception:
                ratings_files = {"home": None, "away": None}
        else:
            ratings_files = {"home": None, "away": None}
        if coverage == "full":
            try:
                rho = get_league_rho(market.get("league"), season=rating_season)
            except Exception:
                rho = RHO_DEFAULT
            # Model-vs-market tension (instability signal). Model-vs-market
            # EDGE lives in edge_pct — the two must not share one penalty.
            total_disagreement = round(abs((lh + la) - market_total), 3)
    elif profile.route == "shadow" and profile.baseline_total:
        # Weak environment prior for visible shadow evaluation only.  It cannot
        # create an Official Pick without team-level ratings.
        history_weight = profile.prior_weight
        adjusted_total = market_total * (1.0 - history_weight) + profile.baseline_total * history_weight
        ratio = market_lh / max(0.1, market_lh + market_la)
        lh, la = adjusted_total * ratio, adjusted_total * (1.0 - ratio)
        source = "market+league-prior"
        coverage = "shadow"
        total_disagreement = round(abs((lh + la) - market_total), 3)
    elif profile.route == "watch":
        # Unvalidated tier: market lambdas unchanged (no prior invented),
        # flagged shadow/watch downstream with strict edge + small stake.
        lh, la = market_lh, market_la
        source = "market-watch"
        coverage = "shadow"
    else:
        lh, la = market_lh, market_la
        coverage = "blocked" if profile.route == "blocked" else "market_only"

    return {
        "home": round(lh, 3),
        "away": round(la, 3),
        "total": round(lh + la, 3),
        "formula_version": FORMULA_VERSION,
        "rho": round(float(rho), 3),
        "total_disagreement": total_disagreement,
        "ratings_files": ratings_files,
        "lambda_source": source,
        "coverage_status": coverage,
        "data_grade": data_grade,
        "league_model": profile.key,
        "coverage_reason": profile.reason,
        "history_weight": round(history_weight, 3),
        "market_total": round(market_total, 3),
        "market_margin": round(market_margin, 3),
        "market_total_line": line,
        "market_margin_source": margin_source,
        "market_ah_line": main_ah[0] if main_ah else None,
        "fair_1x2": tuple(fair_1x2),
        "fair_over": fair_over,
    }


def projection_candidate_status(projection):
    coverage = projection.get("coverage_status")
    if coverage == "full":
        return "official"
    if coverage == "shadow":
        return "shadow"
    return "unsupported"


def build_projection_ou_only(market, *, reason=None):
    """OU-only partial projection: total comes from the complete O/U market,
    the home/away split is ASSUMED neutral and flagged. AH/1X2 picks must
    not use this path (margin unknown); OU picks may, under shadow gates.
    Blocked leagues stay blocked."""
    profile = get_league_profile(market.get("league"))
    if profile.route == "blocked":
        raise ValueError("blocked league cannot use OU-only projection")
    ou = select_main_ou(market.get("odds_ou"))
    if ou is None:
        raise ValueError("OU-only projection requires a complete two-sided O/U market")
    line, over, under = ou
    total, fair_over = fit_total_from_ou(over, under, line)
    home = away = max(0.10, total / 2.0)
    return {
        "home": round(home, 3), "away": round(away, 3), "total": round(total, 3),
        "formula_version": FORMULA_VERSION, "rho": RHO_DEFAULT,
        "ratings_files": {"home": None, "away": None},
        "lambda_source": "market-partial-ou",
        "coverage_status": "shadow", "data_grade": "D", "history_weight": 0.0,
        "league_model": profile.key, "coverage_reason": "OU-only partial; neutral split assumed",
        "fallback_reason": str(reason or "paired markets unavailable"),
        "split_assumed": True,
        "market_total": total, "market_margin": 0.0, "market_total_line": line,
        "market_margin_source": "assumed-neutral", "market_ah_line": None,
        "fair_1x2": (1.0 / 3, 1.0 / 3, 1.0 / 3), "fair_over": fair_over,
    }


def project_match(market, *, strength_weight=None):
    """Single entry point: primary -> paired fallback -> OU-only partial.
    Returns (projection, path) with path in {"primary", "fallback", "ou_only"}.
    Raises the last ValueError when nothing is projectable."""
    err1 = err2 = None
    try:
        return build_projection(market, strength_weight=strength_weight), "primary"
    except ValueError as e:
        err1 = e
    try:
        return build_projection_fallback(market, reason=err1), "fallback"
    except ValueError as e:
        err2 = e
    try:
        return build_projection_ou_only(market, reason=err2), "ou_only"
    except ValueError:
        pass
    raise err1 if err1 is not None else ValueError("no projectable market")


def build_projection_fallback(market, *, reason=None):
    """Recover missing 1X2 from paired O/U + AH; never claim rated coverage.

    No fabricated draw price or league-average score direction is introduced.
    Missing either paired market remains an explicit data failure.
    """
    profile = get_league_profile(market.get("league"))
    if profile.route == "blocked":
        raise ValueError("blocked league cannot use projection fallback")
    ou = select_main_ou(market.get("odds_ou"))
    ah = select_main_ah(market.get("odds_ah"))
    if ou is None or ah is None:
        raise ValueError("fallback requires complete paired O/U and AH markets")
    line, over, under = ou
    total, fair_over = fit_total_from_ou(over, under, line)
    margin, _ = fit_margin_from_ah(total, *ah, prior_margin=0.0)
    bound = max(0.0, total - 0.20)
    margin = max(-bound, min(bound, margin))
    from model import match_probs
    home, away = (total + margin) / 2, (total - margin) / 2
    return {
        "home": round(home, 3), "away": round(away, 3), "total": round(total, 3),
        "formula_version": FORMULA_VERSION, "rho": RHO_DEFAULT,
        "ratings_files": {"home": None, "away": None},
        "lambda_source": "market-fallback",
        "coverage_status": "shadow", "data_grade": "C", "history_weight": 0.0,
        "league_model": profile.key, "coverage_reason": "paired O/U + AH fallback; no independent ratings",
        "fallback_reason": str(reason or "primary projection unavailable"),
        "market_total": total, "market_margin": margin, "market_total_line": line,
        "market_margin_source": "ah", "market_ah_line": ah[0],
        "fair_1x2": match_probs(home, away), "fair_over": fair_over,
    }
