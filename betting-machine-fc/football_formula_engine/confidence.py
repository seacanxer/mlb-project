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
            shown.append(max(value, key=lambda row: (row[2].get('ev', 0), row[1])))
            continue
        if market in ('ah', 'ou'):
            lines = {_line_key(market, row[2]) for row in rows}
            main = min(lines, key=lambda line: (
                min(abs(row[2]['confidence'] - 0.5) for row in rows if _line_key(market, row[2]) == line),
                abs(line), line))
            rows = [row for row in rows if _line_key(market, row[2]) == main]
        shown.append(max(rows, key=lambda row: (row[2]['confidence'], row[2].get('ev', 0), row[1])))
    return shown


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
                    if _line_key(market, row[2]) == main or not row[2].get('gate_reasons')]
        kept.extend(rows)
    return kept
