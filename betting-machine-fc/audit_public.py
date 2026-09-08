"""Read-only production audit; no scan, settlement, lock, or config mutations."""
import json
import time
from urllib.request import Request, urlopen

from main import select_top_picks
from prediction import select_main_ou, select_main_ah


def get(path):
    request = Request('https://fc.texasdrill.me' + path, headers={'User-Agent': 'FC-ReadOnly-Audit/1.0', 'Accept': 'application/json'})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def audit():
    tracker = get('/api/tracker')
    matches = get('/api/matches?limit=200')['matches'] + get('/api/matches?limit=200&offset=200')['matches']
    # Half-goal O/U is binary; reciprocal fair price on Asian lines is not win probability.
    binary = [p for p in tracker['settled'] if p['market'] == 'ou'
              and abs(float(p['pick'].split()[1]) % 1 - 0.5) < 1e-8]
    bins = []
    for lo, hi in [(0, .55), (.55, .60), (.60, .65), (.65, 1.01)]:
        rows = [p for p in binary if lo <= p['probability'] < hi]
        bins.append({'range': [lo, hi], 'n': len(rows),
                     'predicted_mean': round(sum(p['probability'] for p in rows) / len(rows), 4) if rows else None,
                     'actual_rate': round(sum(p['profit'] > 0 for p in rows) / len(rows), 4) if rows else None,
                     'profit': round(sum(p['profit'] for p in rows), 3)})
    candidates = []
    coverage = {}
    for match in matches:
        info = match.get('info', {})
        state = match.get('model', {}).get('coverage_status')
        coverage[state] = coverage.get(state, 0) + 1
        if not time.time() < float(info.get('start_ts') or 0) <= time.time() + 86400:
            continue
        paired = select_main_ou(info.get('odds_ou')) is not None and select_main_ah(info.get('odds_ah')) is not None
        for pick in match.get('picks', []):
            candidates.append(dict(pick, has_both_markets=paired))
    new = select_top_picks(candidates, limit=50, per_market=25, per_match=2, max_odds=2.75)
    old_input = [p for p in candidates if p.get('coverage_status') != 'shadow'
                 or (p.get('conservative_ev', 0) >= .06 and p.get('probability', 0) >= .56)]
    old = select_top_picks([dict(p, has_both_markets=True) for p in old_input], limit=50, per_market=25, per_match=2, max_odds=2.5)
    print(json.dumps({'tracker': tracker['summary'], 'binary_ou_calibration': bins,
                      'coverage': coverage, 'cached_candidates_in_24h': len(candidates),
                      'old_gate_replay': len(old), 'new_gate_replay': len(new),
                      'new_official': sum(p['coverage_status'] == 'full' for p in new),
                      'new_shadow': sum(p['coverage_status'] == 'shadow' for p in new),
                      'note': 'Cached candidate replay only; no missing-fixture fallback or new feed fetch. Historical cohorts mix versions.'}, indent=2))


if __name__ == '__main__':
    audit()
