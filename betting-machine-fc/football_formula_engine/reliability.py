"""Read-only reliability metrics for P(positive payout), including half wins.

Pushes and half losses are non-wins for this unconditional event. ROI uses
actual payout profit, not binary labels. Callers must identify cohort provenance.
"""
import math


def reliability_report(records, *, bucket_count=10):
    if not isinstance(bucket_count, int) or not 1 <= bucket_count <= 100:
        raise ValueError('bucket_count must be 1..100')
    accepted, excluded = [], 0
    for row in records:
        p, y, profit = row.get('probability'), row.get('outcome'), row.get('profit')
        if (not row.get('result_verified') or type(p) not in (int, float)
                or not math.isfinite(p) or not 0 <= p <= 1 or y not in (0, 1)
                or type(profit) not in (int, float) or not math.isfinite(profit)):
            excluded += 1
            continue
        accepted.append(row)
    n = len(accepted)
    buckets = []
    for index in range(bucket_count):
        rows = [r for r in accepted if min(int(r['probability'] * bucket_count), bucket_count - 1) == index]
        if not rows:
            continue
        predicted = sum(r['probability'] for r in rows) / len(rows)
        realized = sum(r['outcome'] for r in rows) / len(rows)
        buckets.append({'lower': index / bucket_count, 'upper': (index + 1) / bucket_count,
                        'n': len(rows), 'predicted': predicted, 'realized': realized,
                        'gap_realized_minus_predicted': realized - predicted})
    wins = sum(r['profit'] > 0 for r in accepted)
    losses = sum(r['profit'] < 0 for r in accepted)
    profit = sum(r['profit'] for r in accepted)
    def loss(row):
        p = min(1 - 1e-15, max(1e-15, row['probability']))
        return -(row['outcome'] * math.log(p) + (1 - row['outcome']) * math.log1p(-p))
    return {'n': n, 'excluded': excluded, 'wins': wins, 'losses': losses,
            'pushes': n - wins - losses,
            'win_rate_decided': wins / (wins + losses) if wins + losses else None,
            'positive_payout_rate': wins / n if n else None,
            'profit_units': profit if n else None, 'roi_pct': 100 * profit / n if n else None,
            'brier': sum((r['probability'] - r['outcome']) ** 2 for r in accepted) / n if n else None,
            'log_loss': sum(map(loss, accepted)) / n if n else None,
            'ece': sum(b['n'] * abs(b['gap_realized_minus_predicted']) for b in buckets) / n if n else None,
            'log_loss_clip': 1e-15, 'buckets': buckets}
