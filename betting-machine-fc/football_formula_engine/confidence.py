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
    # name, minimum confidence, historical hit rate (Pinnacle no-vig source)
    ('TINGGI', 0.65, 0.741),
    ('SEDANG', 0.55, 0.601),
    ('RENDAH', 0.45, 0.519),
    ('SPEKULATIF', 0.0, 0.405),
)
DISPLAY_ORDER = ('1x2', 'ah', 'ou', 'btts')


def confidence_tier(probability):
    for name, floor, _hit in TIERS:
        if probability is not None and probability >= floor:
            return name
    return 'SPEKULATIF'


def tier_hit_rate(tier):
    return next((hit for name, _floor, hit in TIERS if name == tier), None)


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
