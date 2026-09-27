"""Conservative result disambiguation shared by both score feeds."""
from datetime import date


def unique_result(candidates, kickoff_date):
    """Prefer exact date, allow one-day provider timezone drift, reject ambiguity.

    Provider IDs from different namespaces are deliberately not compared.
    Missing dates cannot establish historical fixture identity.
    """
    ranked = {}
    for row in candidates:
        try:
            event_date = date.fromisoformat(row['date_key'])
            distance = abs((event_date - kickoff_date).days) if kickoff_date else 0
        except (KeyError, TypeError, ValueError):
            continue
        if distance > 1:
            continue
        identity = (row.get('home'), row.get('away'), row.get('date_key'),
                    row.get('fs_id'), row.get('league'),
                    row.get('home_goals', row.get('home_score')),
                    row.get('away_goals', row.get('away_score')))
        ranked.setdefault(distance, {})[identity] = row
    if not ranked:
        return None
    best = ranked[min(ranked)]
    return next(iter(best.values())) if len(best) == 1 else None
