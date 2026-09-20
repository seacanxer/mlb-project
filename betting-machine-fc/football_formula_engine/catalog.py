"""Display forecasts separately from value-qualified, unvalidated watch picks.

No quotas by direction: both sides use identical payout math and thresholds.
The display line is the bookmaker's most balanced complete pair, so choosing
an extreme line for its high win probability cannot masquerade as confidence.
"""
MARKET_ORDER = ('1x2', 'ah', 'ou', 'btts')
POLICY_VERSION = 'fc-market-catalog-v2'


def select_markets(opportunities):
    forecasts, value_picks = [], []
    for market in MARKET_ORDER:
        rows = [row for row in opportunities if row[0] == market]
        if not rows:
            continue
        eligible = [row for row in rows if not row[2]['gate_reasons']]
        if eligible:
            value_picks.append(max(eligible, key=lambda row: (row[2]['conservative_ev'], row[1])))
        if market in ('ah', 'ou'):
            # Opposing AH signs are the same line when expressed for home.
            def line_key(row):
                offer = row[2]
                line = offer['line_quarters']
                return -line if market == 'ah' and offer['side'] == 'away' else line
            lines = sorted({line_key(row) for row in rows})
            main_line = min(lines, key=lambda line: (
                min(abs(row[2]['market_probability'] - 0.5) for row in rows if line_key(row) == line),
                abs(line), line))
            rows = [row for row in rows if line_key(row) == main_line]
        # 1X2 displays the most probable result. Binary priced markets display
        # the better expected return on a fixed line, treating both signs alike.
        score = 'probability' if market == '1x2' else 'ev'
        forecasts.append(max(rows, key=lambda row: (row[2][score], row[1])))
    return forecasts, value_picks


def direction_counts(rows):
    counts = {key: 0 for key in ('over', 'under', 'ah_plus', 'ah_minus', 'ah_zero', 'btts_yes', 'btts_no')}
    for market, _label, offer in rows:
        if market == 'ou':
            counts[offer['side']] += 1
        elif market == 'ah':
            line = offer['line_quarters']
            counts['ah_plus' if line > 0 else 'ah_minus' if line < 0 else 'ah_zero'] += 1
        elif market == 'btts':
            counts['btts_' + offer['side']] += 1
    return counts
