# ============================================================================
# match_prediction.py — Match Prediction Insight Card engine
#
# Computes a full prediction card for any fixture:
#   - 1X2 probabilities from Dixon-Coles bivariate Poisson score matrix
#   - xG diff, total goals estimate
#   - BTTS Yes/No probability
#   - Asian Handicap probabilities (integer, half, quarter lines)
#   - Over/Under probabilities
#   - Priced recommendations from the shared quality policy
#
# All markets are derived from ONE score matrix to ensure mathematical
# consistency (PRD §4.4).
#
# Reuses existing model.py functions; does NOT duplicate the math.
# ============================================================================
import math
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from model import (
    RHO_DEFAULT,
    btts_prob,
    dixon_coles_tau,
    match_probs,
    over_prob,
    pois_pmf,
    score_matrix as model_score_matrix,
    under_prob,
)


from model import MAX_GOALS
from market_quality import outcome_distribution


def build_full_matrix(lh, la, rho=RHO_DEFAULT):
    """Build the shared engine's score matrix as a JSON-serializable 2D list.

    Returns matrix_2d where matrix_2d[i][j] = P(home=i, away=j).
    The matrix is normalised so probabilities sum to 1.0.
    """
    raw, _ = model_score_matrix(lh, la, rho)
    return [[raw[(i, j)] for j in range(MAX_GOALS + 1)] for i in range(MAX_GOALS + 1)]


def matrix_1x2(matrix):
    """Derive 1X2 probabilities from a 2D score matrix."""
    n = len(matrix)
    home = draw = away = 0.0
    for i in range(n):
        for j in range(n):
            p = matrix[i][j]
            if i > j:
                home += p
            elif i == j:
                draw += p
            else:
                away += p
    return round(home, 4), round(draw, 4), round(away, 4)


def matrix_btts(matrix):
    """BTTS Yes probability from score matrix."""
    n = len(matrix)
    yes = 0.0
    for i in range(1, n):
        for j in range(1, n):
            yes += matrix[i][j]
    return round(yes, 4)


def matrix_over_under(matrix, line):
    """Expected winning stake fractions; excluded mass is refunded stake."""
    flat = {(i, j): p for i, row in enumerate(matrix) for j, p in enumerate(row)}
    over = outcome_distribution(flat, "ou", "over", line)
    under = outcome_distribution(flat, "ou", "under", line)
    return round(over["win_fraction"], 4), round(under["win_fraction"], 4)


def matrix_ah(matrix, side, line):
    """Asian Handicap probability from score matrix.

    side: 'home' or 'away'
    line: handicap line from the perspective of the chosen side
          (e.g. home -0.5 means home gives half a goal)

    Supports integer, half, and quarter lines.
    Returns (win_prob, push_prob, lose_prob).
    """
    n = len(matrix)
    # Quarter-line: split into two half-stakes
    frac = abs(line) % 0.5
    if frac > 0.01 and frac < 0.49:
        # Quarter line — average of two adjacent half/integer lines
        line_lo = line - 0.25 if line > 0 else line + 0.25
        line_hi = line + 0.25 if line > 0 else line - 0.25
        # For negative lines like -0.25: sub-lines are 0 and -0.5
        if abs(line % 0.5) > 0.1:
            line_lo = math.floor(line * 2) / 2.0
            line_hi = math.ceil(line * 2) / 2.0
        w1, p1, l1 = _ah_single(matrix, side, line_lo)
        w2, p2, l2 = _ah_single(matrix, side, line_hi)
        return (
            round((w1 + w2) / 2, 4),
            round((p1 + p2) / 2, 4),
            round((l1 + l2) / 2, 4),
        )
    return _ah_single(matrix, side, line)


def _ah_single(matrix, side, line):
    """Single AH line calculation (integer or half)."""
    n = len(matrix)
    win = push = lose = 0.0
    for i in range(n):
        for j in range(n):
            p = matrix[i][j]
            if side == 'home':
                diff = (i - j) + line
            else:
                diff = (j - i) + line
            if diff > 1e-9:
                win += p
            elif abs(diff) <= 1e-9:
                push += p
            else:
                lose += p
    return round(win, 4), round(push, 4), round(lose, 4)


def _goal_diff_distribution(matrix):
    """Compute P(D=d) where D = home_goals - away_goals."""
    n = len(matrix)
    dist = {}
    for i in range(n):
        for j in range(n):
            d = i - j
            dist[d] = dist.get(d, 0.0) + matrix[i][j]
    return dist


def derive_all_markets(matrix, lh, la):
    """Derive complete prediction card from a score matrix.

    Returns a dict with all market probabilities and recommendations.
    """
    ph, pd, pa = matrix_1x2(matrix)
    btts_yes = matrix_btts(matrix)
    btts_no = round(1.0 - btts_yes, 4)

    xg_diff = round(lh - la, 3)
    total_goals = round(lh + la, 3)

    # 1X2 recommendation
    best_1x2 = 'Home' if ph >= pd and ph >= pa else ('Draw' if pd >= pa else 'Away')

    # Over/Under for common lines
    ou_lines = {}
    for line in [1.5, 2.0, 2.25, 2.5, 2.75, 3.0, 3.5]:
        o, u = matrix_over_under(matrix, line)
        ou_lines[str(line)] = {'over': o, 'under': u, 'push': round(1 - o - u, 4)}

    # Best OU recommendation (pick the line closest to 50/50 and favour the better side)
    best_ou_line = 2.5
    best_ou_side = 'over' if ou_lines['2.5']['over'] > 0.5 else 'under'
    best_ou_prob = ou_lines['2.5'][best_ou_side]

    # Asian Handicap for common lines (home perspective)
    ah_lines = {}
    for line in [-2.0, -1.75, -1.5, -1.25, -1.0, -0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]:
        w_h, p_h, l_h = matrix_ah(matrix, 'home', line)
        ah_lines[str(line)] = {'home_win': w_h, 'push': p_h, 'home_lose': l_h}

    # Recommend AH: pick the line where the favorite side is closest to ~55-60%
    best_ah_side = 'home' if xg_diff > 0 else 'away'
    best_ah_line = 0.0
    best_ah_prob = 0.5
    for line_str, probs in ah_lines.items():
        line_val = float(line_str)
        if best_ah_side == 'home':
            prob = probs['home_win']
        else:
            # For away, flip the line perspective
            prob = probs['home_lose']
        if 0.50 <= prob <= 0.70 and prob > best_ah_prob:
            best_ah_prob = prob
            best_ah_line = line_val if best_ah_side == 'home' else -line_val

    # BTTS recommendation
    best_btts = 'Yes' if btts_yes > 0.5 else 'No'

    # Top predicted scores
    n = len(matrix)
    score_probs = []
    for i in range(n):
        for j in range(n):
            score_probs.append({
                'score': f'{i}-{j}',
                'home': i,
                'away': j,
                'prob': round(matrix[i][j], 4),
            })
    score_probs.sort(key=lambda x: x['prob'], reverse=True)

    return {
        'one_x_two': {'home': ph, 'draw': pd, 'away': pa},
        'xg_diff': xg_diff,
        'total_goals': total_goals,
        'favorite': 'Home' if xg_diff > 0.05 else ('Away' if xg_diff < -0.05 else 'Neutral'),
        'btts': {'yes': btts_yes, 'no': btts_no},
        'ou_lines': ou_lines,
        'ah_lines': ah_lines,
        'recommended': {
            '1x2': best_1x2,
            'ah': {
                'side': best_ah_side,
                'line': best_ah_line,
                'prob': best_ah_prob,
            },
            'ou': {
                'line': best_ou_line,
                'side': best_ou_side,
                'prob': best_ou_prob,
            },
            'btts': best_btts,
        },
        'top_scores': score_probs[:8],
        'lambdas': {'home': round(lh, 3), 'away': round(la, 3)},
    }


def compute_prediction_card(match_data, beta_squad=0.0, home_advantage_override=None,
                            manual_adj_home=1.0, manual_adj_away=1.0,
                            rho=None):
    """Compute the full prediction card for a match.

    match_data: a dict from matches_detailed.json (has 'info', 'lambdas', 'model', etc.)
    beta_squad: weight of squad-value modifier (0.0 = pure history/market, 0.4 = max)
    home_advantage_override: override home advantage factor (None = use model default)
    manual_adj_home/away: multiplier for manual adjustments (1.0 = no change)
    rho: Dixon-Coles correlation parameter, or None to follow the match's
    league rho from the projection (same assumption Top Picks used).

    Returns the full card dict ready for the API response.
    """
    model_rho_in = (match_data.get('model') or {}).get('rho')
    try:
        model_rho = float(model_rho_in)
    except (TypeError, ValueError):
        model_rho = RHO_DEFAULT
    eff_rho = float(rho) if rho is not None else model_rho
    # Extract base lambdas from the existing model output
    lambdas = match_data.get('lambdas', {})
    lh = float(lambdas.get('home') or 0)
    la = float(lambdas.get('away') or 0)
    if not all(math.isfinite(v) and v > 0 for v in (lh, la)):
        raise ValueError("valid model lambdas required; no default prediction")

    # Layer 2: Squad value adjustment (β modifier)
    # In phase 1, β adjusts the home/away strength ratio without actual squad values
    # A positive β slightly amplifies the existing strength differential
    if beta_squad != 0:
        raise ValueError("squad adjustment unavailable: no verified squad-value input")

    # Home advantage override
    if home_advantage_override is not None:
        # The model already includes home_adv (~1.08). If user overrides to 1.15,
        # we apply the ratio: new_adv / default_adv
        default_adv = match_data.get('model', {}).get('home_advantage')
        if not default_adv:
            raise ValueError("home advantage override requires the actual model baseline")
        adv_ratio = float(home_advantage_override) / default_adv
        lh *= adv_ratio

    # Manual adjustments
    lh *= float(manual_adj_home)
    la *= float(manual_adj_away)

    # Ensure sane bounds
    lh = max(0.15, min(5.0, lh))
    la = max(0.15, min(5.0, la))

    # Build the full score matrix
    matrix = build_full_matrix(lh, la, eff_rho)

    # Derive all markets
    result = derive_all_markets(matrix, lh, la)
    result['model_lean'] = result.pop('recommended')
    result['recommended'] = {'1x2': 'NO BET', 'ah': None, 'ou': None, 'btts': 'NO BET'}
    from main import analyze_match, select_top_picks
    from prediction import FORMULA_VERSION
    import time
    scenario = manual_adj_home != 1 or manual_adj_away != 1 or (rho is not None and float(rho) != model_rho) or home_advantage_override is not None
    stale = (match_data.get('model', {}).get('formula_version') != FORMULA_VERSION
             or float(match_data.get('info', {}).get('start_ts') or 0) <= time.time())
    eligible = [] if scenario or stale else select_top_picks(analyze_match(
        match_data.get('info', {}), lh, la, projection_meta=match_data.get('model', {})), limit=1, per_match=1)
    result['qualified_picks'] = eligible
    result['decision'] = 'CANDIDATE' if eligible else 'NO BET'
    result['decision_reason'] = 'Manual scenario only' if scenario else ('Refresh required or fixture already started' if stale else ('Quality gates passed; estimates not calibrated' if eligible else 'No offered price passes the shared quality gates'))
    for pick in eligible:
        side, line = pick['pick'].split()[:2]
        result['recommended'][pick['market']] = {'side': side.lower(), 'line': float(line), 'prob': pick['probability'], 'odds': pick['odds']}

    # Attach match info
    info = match_data.get('info', {})
    result['match_info'] = {
        'home': info.get('home', ''),
        'away': info.get('away', ''),
        'league': info.get('league', ''),
        'start_ts': info.get('start_ts', 0),
        'match_id': str(info.get('match_id', info.get('id', ''))),
    }

    # Attach score matrix for client-side recomputation
    result['score_matrix'] = matrix

    # Attach model metadata
    model_meta = match_data.get('model', {})
    result['model_meta'] = {
        'lambda_source': model_meta.get('lambda_source', 'unknown'),
        'coverage_status': model_meta.get('coverage_status', 'unknown'),
        'data_grade': model_meta.get('data_grade', 'D'),
        'formula_version': model_meta.get('formula_version', ''),
        'calibration_status': 'unvalidated',
        'scenario_only': scenario,
    }

    # Attach parameters used
    result['parameters'] = {
        'beta_squad': round(beta_squad, 3),
        'home_advantage': home_advantage_override if home_advantage_override is not None else model_meta.get('home_advantage'),
        'manual_adj_home': round(float(manual_adj_home), 3),
        'manual_adj_away': round(float(manual_adj_away), 3),
        'rho': round(eff_rho, 3),
    }

    return result
