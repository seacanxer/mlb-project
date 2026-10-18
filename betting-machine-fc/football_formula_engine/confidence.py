"""Card projections with a confidence tier instead of elimination.

A projection is the most likely side of each market on the bookmaker's
balanced (main) line. Its confidence is the best-calibrated probability
available: the sharp book's no-vig price when matched, otherwise the 1xbit
no-vig price. The goal model's own probability is shown separately; the
walk-forward replay found it overconfident and uninformative against price.

Tier hit rates below were measured on 27,390 historical fixtures (pick = most
likely side at the no-vig price, Pinnacle as source). They describe how often
the pick wins, not profit: without a price edge, ROI is about minus margin.
Value (edge >= 2% against the sharp price) is flagged separately.
"""
TIERS = (
    # name, minimum confidence
    ('TINGGI', 0.65),
    ('SEDANG', 0.55),
    ('RENDAH', 0.45),
    ('SPEKULATIF', 0.0),
)
# Historical hit rate per tier and confidence source (walk-forward replay,
# pick = most likely side). 'model' is the DC goal model pooled with market
# goals (the card's model lane); raw DC alone was overconfident (TINGGI tier
# won 61%) and is never used as confidence.
TIER_HIT_RATES = {
    'sharp': {'TINGGI': 0.741, 'SEDANG': 0.601, 'RENDAH': 0.519, 'SPEKULATIF': 0.405},
    'model': {'TINGGI': 0.692, 'SEDANG': 0.572, 'RENDAH': 0.509, 'SPEKULATIF': 0.402},
    'market': {'TINGGI': 0.743, 'SEDANG': 0.599, 'RENDAH': 0.514, 'SPEKULATIF': 0.405},
}
SOURCE_LABELS = {
    'sharp': 'Pinnacle (sharp)',
    'model': 'Model DC + pasar',
    'national_model': 'Model tim nasional + pasar',
    'market': 'Harga pasar 1xbit',
}
DISPLAY_ORDER = ('1x2', 'ah', 'ou', 'btts')
# Below this the "most likely side" is a coin flip after margin (replay: the
# 45-55% tier won 51.9%, ROI about -3%). Such markets are shown as balanced,
# not as a pick, so two near-50/50 sides cannot read as opposing advice.
MIN_LEAN_CONFIDENCE = 0.55
# When the balanced AH/O-U line is a coin flip, show the offered alternative
# line with a clear direction instead (e.g. Lazio +1.5 rather than Lazio +1):
# confidence >= ALT_MIN_CONFIDENCE at odds >= ALT_MIN_ODDS, choosing the
# highest odds that qualify. Tested and rejected as tie-breakers: rolling shots
# on target, goals, rest days and Pinnacle-vs-Bet365 divergence; when they
# disagreed with the market they were right 49-53% (walk-forward, 2024-26).
ALT_MIN_CONFIDENCE = 0.60
ALT_MIN_ODDS = 1.40


def confidence_tier(probability):
    for name, floor in TIERS:
        if probability is not None and probability >= floor:
            return name
    return 'SPEKULATIF'


def tier_hit_rate(tier, source='sharp'):
    """Historical hit rate for a tier from a given source; None when unmeasured."""
    return TIER_HIT_RATES.get(source, {}).get(tier)


def source_label(source, national=False):
    if source == 'model' and national:
        return SOURCE_LABELS['national_model']
    return SOURCE_LABELS.get(source, source)


def _line_key(market, offer):
    line = offer['line_quarters']
    return -line if market == 'ah' and offer['side'] == 'away' else line


def display_markets(opportunities):
    """One projection per market: the value candidate if any, else the most confident side
    on the main line. Never filtered out for lacking value."""
    shown = []
    for market in DISPLAY_ORDER:
        rows = [row for row in opportunities if row[0] == market and row[2].get('confidence') is not None]
        if not rows:
            continue
        # A value candidate (no gate reasons) is the actionable pick for this
        # market; show it, with its own confidence, instead of the favourite.
        value = [row for row in rows if not row[2].get('gate_reasons')]
        if value:
            best = max(value, key=lambda row: (row[2].get('ev', 0), row[1]))
            best[2]['display_status'] = 'value'
            shown.append(best)
            continue
        all_rows = [row for row in opportunities if row[0] == market and row[2].get('confidence') is not None]
        if market in ('ah', 'ou'):
            lines = {_line_key(market, row[2]) for row in rows}
            main = min(lines, key=lambda line: (
                min(abs(row[2]['confidence'] - 0.5) for row in rows if _line_key(market, row[2]) == line),
                abs(line), line))
            rows = [row for row in rows if _line_key(market, row[2]) == main]
        best = max(rows, key=lambda row: (row[2]['confidence'], row[2].get('ev', 0), row[1]))
        if best[2]['confidence'] >= MIN_LEAN_CONFIDENCE:
            best[2]['display_status'] = 'pick'
        else:
            alternatives = [row for row in all_rows if market in ('ah', 'ou')
                            and row[2]['confidence'] >= ALT_MIN_CONFIDENCE
                            and float(row[2].get('odds') or 0) >= ALT_MIN_ODDS]
            if alternatives:
                alt = max(alternatives, key=lambda row: (float(row[2]['odds']), row[2]['confidence'], row[1]))
                alt[2]['display_status'] = 'alt_line'
                alt[2]['main_line_confidence'] = best[2]['confidence']
                best = alt
            else:
                best[2]['display_status'] = 'no_lean'
        shown.append(best)
    return shown


def score_scenario(distribution, home_name=None, away_name=None):
    """Margin breakdown from the same score matrix every market is priced from.
    It explains why e.g. 'Home to win' and 'Away +1' can both be the likelier
    side: a narrow one-goal home win satisfies the first and refunds the second."""
    home = draw = away = home_by1 = home_by2 = away_by1 = away_by2 = 0.0
    for x, y, p in distribution.cells():
        if x > y:
            home += p
            if x - y == 1:
                home_by1 += p
            else:
                home_by2 += p
        elif x == y:
            draw += p
        else:
            away += p
            if y - x == 1:
                away_by1 += p
            else:
                away_by2 += p
    favourite = 'home' if home >= away else 'away'
    return {'home_win': round(home, 4), 'draw': round(draw, 4), 'away_win': round(away, 4),
            'home_by1': round(home_by1, 4), 'home_by2_plus': round(home_by2, 4),
            'away_by1': round(away_by1, 4), 'away_by2_plus': round(away_by2, 4),
            'favourite': favourite,
            'narrow_win_likelier': (home_by1 >= home_by2) if favourite == 'home' else (away_by1 >= away_by2)}


def _main_line(market, rows):
    lines = {_line_key(market, row[2]) for row in rows}
    return min(lines, key=lambda line: (
        min(abs((row[2].get('confidence') or 0.5) - 0.5) for row in rows if _line_key(market, row[2]) == line),
        abs(line), line))


def compact_options(opportunities):
    """Rows worth storing for the card's detail view: every 1X2/BTTS side, both
    sides of the AH/O-U main line, and any value candidate. Alternate book lines
    (often 40+ per fixture) are dropped; they were the bulk of the scan file."""
    kept = []
    for market in DISPLAY_ORDER:
        rows = [row for row in opportunities if row[0] == market]
        if not rows:
            continue
        if market in ('ah', 'ou'):
            main = _main_line(market, rows)
            rows = [row for row in rows
                    if _line_key(market, row[2]) == main or not row[2].get('gate_reasons')
                    or row[2].get('display_status') == 'alt_line']
        kept.extend(rows)
    return kept
