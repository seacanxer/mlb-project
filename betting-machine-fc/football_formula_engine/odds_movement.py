"""Odds movement read from the immutable quote journal.

Every scan records the 1xbit book and, when configured, the Pinnacle
reference for each fixture. Comparing the first and latest complete market
per bookmaker gives the movement of each contract's no-vig probability.

Signals (for the side of a given contract, in probability points):
  soft_lag      Pinnacle moved >= 2pp toward this side and 1xbit followed by
                less than half of that: the soft price is lagging a sharp move.
  steam_with    Pinnacle moved >= 2pp toward this side and 1xbit followed.
  steam_against Pinnacle moved >= 2pp away from this side.
  flat          Pinnacle moved less than 2pp.
  market_with / market_against / market_flat
                Same thresholds on 1xbit alone when no Pinnacle history exists.
  unknown       Fewer than two snapshots or less than 30 minutes of history.

Evidence status: the historical replay only has open and close prices, so
it can say that backing a move after it happened lost and that the current
sharp price already contains it. It cannot test intraday signals. These
signals therefore only order picks and add warnings; they are logged with
every projection so scripts/fc-movement-report.py can validate them on
graded live results before they are allowed to gate anything.
"""
from .sharp_reference import fair_probabilities

MOVE_THRESHOLD = 0.02
LAG_RATIO = 0.5
MIN_SPAN_SECONDS = 1800
SIGNAL_RANK = {'soft_lag': 0, 'steam_with': 1, 'market_with': 2, 'flat': 3, 'market_flat': 3,
               'unknown': 3, 'market_against': 4, 'steam_against': 5}
SIGNAL_LABELS = {
    'soft_lag': 'Pinnacle bergerak ke sisi ini, 1xbit belum mengikuti',
    'steam_with': 'Pinnacle dan 1xbit bergerak ke sisi ini',
    'steam_against': 'Pinnacle bergerak melawan sisi ini',
    'flat': 'Harga Pinnacle stabil',
    'market_with': 'Odds 1xbit turun untuk sisi ini (pasar mendukung)',
    'market_against': 'Odds 1xbit naik untuk sisi ini (pasar melawan)',
    'market_flat': 'Odds 1xbit stabil',
    'unknown': 'Riwayat odds belum cukup',
}


def _quotes(obs):
    return {(q['market'], q['side'], q['line_quarters']): {'decimal_odds': float(q['decimal_odds'])}
            for q in obs.get('quotes') or []}


def movement_series(observations, bookmaker):
    """{contract: {'open', 'now', 'open_at', 'now_at', 'snapshots'}} for one bookmaker.

    Each snapshot's probability comes from a complete market inside a single
    observation, so a side is never paired with a stale opposite side.
    """
    series = {}
    for obs in sorted((o for o in observations if str(o.get('bookmaker', '')).lower() == bookmaker.lower()),
                      key=lambda o: o.get('captured_at') or 0):
        at = obs.get('captured_at')
        for contract, probability in fair_probabilities(_quotes(obs)).items():
            row = series.get(contract)
            if row is None:
                series[contract] = {'open': probability, 'now': probability, 'open_at': at,
                                    'now_at': at, 'snapshots': 1}
            else:
                row.update(now=probability, now_at=at, snapshots=row['snapshots'] + 1)
    return series


def _span(row):
    if not row or row['open_at'] is None or row['now_at'] is None:
        return 0
    return row['now_at'] - row['open_at']


def classify(reference_row, primary_row):
    """Signal for one contract side from reference (Pinnacle) and primary (1xbit) series."""
    if reference_row and reference_row['snapshots'] >= 2 and _span(reference_row) >= MIN_SPAN_SECONDS:
        ref_move = reference_row['now'] - reference_row['open']
        prim_move = (primary_row['now'] - primary_row['open']) if primary_row else 0.0
        if ref_move >= MOVE_THRESHOLD:
            return 'soft_lag' if prim_move < LAG_RATIO * ref_move else 'steam_with'
        if ref_move <= -MOVE_THRESHOLD:
            return 'steam_against'
        return 'flat'
    if primary_row and primary_row['snapshots'] >= 2 and _span(primary_row) >= MIN_SPAN_SECONDS:
        move = primary_row['now'] - primary_row['open']
        if move >= MOVE_THRESHOLD:
            return 'market_with'
        if move <= -MOVE_THRESHOLD:
            return 'market_against'
        return 'market_flat'
    return 'unknown'


def annotate(offer, contract, reference_series, primary_series):
    """Attach movement fields to a priced offer in place."""
    ref = reference_series.get(contract)
    prim = primary_series.get(contract)
    signal = classify(ref, prim)
    offer['reference_open_probability'] = ref['open'] if ref else None
    offer['reference_move'] = (ref['now'] - ref['open']) if ref else None
    offer['primary_open_probability'] = prim['open'] if prim else None
    offer['primary_move'] = (prim['now'] - prim['open']) if prim else None
    offer['movement_signal'] = signal
    offer['movement_span_minutes'] = round(max(_span(ref), _span(prim)) / 60) if (ref or prim) else 0
    offer['movement_snapshots'] = max(ref['snapshots'] if ref else 0, prim['snapshots'] if prim else 0)
    return signal
