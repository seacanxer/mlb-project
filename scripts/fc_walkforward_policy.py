"""Stage 2 of the FC walk-forward replay: decision-policy evaluation.

Reads fixture records written by ``fc-walkforward-backtest.py build`` and
replays the live decision path (goal blend -> score matrix -> payout-aware
EV -> gates -> card/value selection) for a set of candidate policies.

The score matrix and payout arithmetic are vectorised re-implementations of
``score_matrix``/``markets``; ``check_parity`` compares them with the engine on
a sample before any result is reported. Card selection calls the engine's own
``catalog.select_markets`` so the replay cannot drift from production rules.
"""
import json
import math
import os
import random
import sys
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'betting-machine-fc'))

from football_formula_engine.catalog import select_markets  # noqa: E402
from football_formula_engine.markets import asian_handicap, match_odds, over_under  # noqa: E402
from football_formula_engine.score_matrix import build_score_matrix  # noqa: E402

MAX_GOALS = 20
GOALS = np.arange(MAX_GOALS + 1)
LOG_FACT = np.array([math.lgamma(k + 1) for k in GOALS])
OUTCOMES = ('full_win', 'half_win', 'push', 'half_loss', 'full_loss')
DEV_SEASONS = ('2223', '2324')
TEST_SEASONS = ('2425', '2526')


@dataclass(frozen=True)
class Policy:
    name: str
    goal_book: str = 'b365'          # book used to infer market goal rates
    novig_book: str | None = None    # book used for the no-vig benchmark (None -> price book)
    price_book: str = 'b365'         # executable price used for EV and settlement
    market_weight: float = 0.65      # geometric pool weight on market goals
    anchor: dict = field(default_factory=lambda: {'ah': 0.5, 'btts': 0.5})
    odds_floor: float = 1.6
    odds_cap: float = 2.5
    ev_gate: float = 0.01
    penalty: float = 0.02
    max_gap: float = 0.15
    ev_cap: float | None = None      # reject implausibly large EV (model error)
    markets: tuple = ('1x2', 'ah', 'ou')
    second_pick_min_cev: float = 0.02
    max_picks: int = 2


# ---------------------------------------------------------------------------
# Vectorised score-distribution arithmetic
# ---------------------------------------------------------------------------

def poisson(rate):
    values = np.exp(-rate + GOALS * math.log(rate) - LOG_FACT)
    return values


def score_matrix(home, away, rho=0.0):
    matrix = np.outer(poisson(home), poisson(away))
    if rho:
        matrix[0, 0] *= 1 - home * away * rho
        matrix[1, 0] *= 1 + away * rho
        matrix[0, 1] *= 1 + home * rho
        matrix[1, 1] *= 1 - rho
    return matrix / matrix.sum()


DIFF = np.subtract.outer(GOALS, GOALS)      # home - away
TOTAL = np.add.outer(GOALS, GOALS)


def _component(measure):
    return np.sign(measure)  # 1 win, 0 push, -1 loss


def _split(line_quarters):
    return (line_quarters - 1, line_quarters + 1) if abs(line_quarters) % 2 else (line_quarters, line_quarters)


def _payout_from_measure(matrix, measure_quarters_fn, line_quarters):
    first, second = _split(line_quarters)
    a = _component(measure_quarters_fn(first))
    b = _component(measure_quarters_fn(second))
    s = a + b
    return (float(matrix[s == 2].sum()), float(matrix[s == 1].sum()), float(matrix[(s == 0) & (a == 0)].sum()),
            float(matrix[s == -1].sum()), float(matrix[s == -2].sum()) + float(matrix[(s == 0) & (a != 0)].sum()))


def ah_payout(matrix, side, line_quarters):
    margin = DIFF if side == 'home' else -DIFF
    return _payout_from_measure(matrix, lambda line: 4 * margin + line, line_quarters)


def ou_payout(matrix, side, line_quarters):
    if side == 'over':
        return _payout_from_measure(matrix, lambda line: 4 * TOTAL - line, line_quarters)
    return _payout_from_measure(matrix, lambda line: line - 4 * TOTAL, line_quarters)


def one_x_two(matrix):
    home = float(matrix[DIFF > 0].sum())
    draw = float(matrix[DIFF == 0].sum())
    return {'home': (home, 0, 0, 0, 1 - home), 'draw': (draw, 0, 0, 0, 1 - draw),
            'away': (1 - home - draw, 0, 0, 0, home + draw)}


def point_mass(hg, ag):
    matrix = np.zeros((MAX_GOALS + 1, MAX_GOALS + 1))
    matrix[min(hg, MAX_GOALS), min(ag, MAX_GOALS)] = 1.0
    return matrix


def check_parity(samples=200, seed=7):
    rng = random.Random(seed)
    worst = 0.0
    for _ in range(samples):
        home, away = rng.uniform(0.3, 3.2), rng.uniform(0.3, 3.0)
        engine = build_score_matrix(home, away, 0.0)
        mine = score_matrix(home, away)
        e1, m1 = match_odds(engine), one_x_two(mine)
        for side in ('home', 'draw', 'away'):
            worst = max(worst, abs(e1[side].full_win - m1[side][0]))
        for q in (-7, -6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 5, 6):
            for side in ('home', 'away'):
                ep = asian_handicap(engine, side, q)
                mp = ah_payout(mine, side, q)
                worst = max(worst, max(abs(getattr(ep, k) - v) for k, v in zip(OUTCOMES, mp)))
        for q in (6, 8, 9, 10, 11, 12, 14):
            for side in ('over', 'under'):
                ep = over_under(engine, side, q)
                mp = ou_payout(mine, side, q)
                worst = max(worst, max(abs(getattr(ep, k) - v) for k, v in zip(OUTCOMES, mp)))
    if worst > 1e-6:
        raise SystemExit(f'Vectorised payout parity failed: max abs diff {worst:.2e}')
    return worst


# ---------------------------------------------------------------------------
# Value arithmetic (ports of value.py / market_safety.py, pure-Python tuples)
# ---------------------------------------------------------------------------

def win_loss(p):
    return p[0] + 0.5 * p[1], p[4] + 0.5 * p[3]


def ev_of(p, odds):
    win, loss = win_loss(p)
    return (odds - 1) * win - loss


def anchor(p, market_probability, weight):
    win, loss = win_loss(p)
    raw = win / (win + loss) if win + loss else None
    if raw is None or win == 0 or loss == 0 or weight == 1:
        return p, raw
    win_mass, loss_mass = p[0] + p[1], p[4] + p[3]
    win_factor, loss_factor = win / win_mass, loss / loss_mass
    target = weight * raw + (1 - weight) * market_probability
    adjusted = target * loss_factor * (1 - p[2]) / ((1 - target) * win_factor + target * loss_factor)
    a, b = adjusted / win_mass, (1 - p[2] - adjusted) / loss_mass
    return (p[0] * a, p[1] * a, p[2], p[3] * b, p[4] * b), raw


def no_vig(prices):
    implied = [1 / x for x in prices]
    total = sum(implied)
    return [x / total for x in implied]


def blend(model, market, weight):
    if market is None:
        return model
    return tuple(math.exp((1 - weight) * math.log(m) + weight * math.log(k)) for m, k in zip(model, market))


# ---------------------------------------------------------------------------
# Opportunity construction and selection
# ---------------------------------------------------------------------------

def opportunities(record, policy, matrix):
    odds = record['odds']
    nv_book = policy.novig_book or policy.price_book
    out = []

    def offer(market, side, label, payout, price, nv, line_quarters, settle):
        payout, raw_price_probability = anchor(payout, nv, policy.anchor.get(market, 1.0))
        win, loss = win_loss(payout)
        ev = ev_of(payout, price)
        cev = ev - policy.penalty
        reasons = []
        if raw_price_probability is not None and abs(raw_price_probability - nv) > policy.max_gap:
            reasons.append('MODEL_MARKET_DISAGREEMENT')
        if not (policy.odds_floor <= price <= policy.odds_cap):
            reasons.append('ODDS_OUTSIDE_VALUE_RANGE')
        if ev < policy.ev_gate:
            reasons.append('EV_BELOW_VALUE_THRESHOLD')
        if cev < 0:
            reasons.append('CONSERVATIVE_EV_BELOW_THRESHOLD')
        if policy.ev_cap is not None and ev > policy.ev_cap:
            reasons.append('EV_IMPLAUSIBLE')
        reasons.extend(record.get('model_reasons') or [])
        out.append((market, label, {
            'odds': price, 'ev': ev, 'conservative_ev': cev, 'probability': payout[0] + payout[1],
            'effective_win_probability': win, 'market_probability': nv, 'gate_reasons': reasons,
            'side': side, 'line_quarters': line_quarters, '_settle': settle,
            '_payout': payout,
        }))

    if '1x2' in policy.markets and odds.get(f'{policy.price_book}_1x2') and odds.get(f'{nv_book}_1x2'):
        prices = odds[f'{policy.price_book}_1x2']
        nv = no_vig(odds[f'{nv_book}_1x2'])
        payouts = one_x_two(matrix)
        for i, (side, label) in enumerate((('home', 'Home'), ('draw', 'Draw'), ('away', 'Away'))):
            offer('1x2', side, label, payouts[side], prices[i], nv[i], None, ('1x2', side, None))
    if 'ou' in policy.markets and odds.get(f'{policy.price_book}_ou') and odds.get(f'{nv_book}_ou'):
        prices = odds[f'{policy.price_book}_ou']
        nv = no_vig(odds[f'{nv_book}_ou'])
        for i, side in enumerate(('over', 'under')):
            offer('ou', side, f'{side.title()} 2.5', ou_payout(matrix, side, 10), prices[i], nv[i], 10,
                  ('ou', side, 10))
    if ('ah' in policy.markets and 'AHh' in odds and odds.get(f'{policy.price_book}_ah')
            and odds.get(f'{nv_book}_ah')):
        q = int(round(odds['AHh'] * 4))
        prices = odds[f'{policy.price_book}_ah']
        nv = no_vig(odds[f'{nv_book}_ah'])
        offer('ah', 'home', f'AH Home {odds["AHh"]:+g}', ah_payout(matrix, 'home', q), prices[0], nv[0], q,
              ('ah', 'home', q))
        offer('ah', 'away', f'AH Away {-odds["AHh"]:+g}', ah_payout(matrix, 'away', -q), prices[1], nv[1], -q,
              ('ah', 'away', -q))
    return out


def card_eligible(offer):
    return (offer.get('ev', -1) > 0 and offer.get('conservative_ev', -1) >= 0
            and 'MODEL_MARKET_DISAGREEMENT' not in offer['gate_reasons']
            and 'EV_IMPLAUSIBLE' not in offer['gate_reasons'])


def value_picks(opps, policy):
    best = {}
    for row in opps:
        offer = row[2]
        if offer['gate_reasons'] or not card_eligible(offer):
            continue
        if row[0] not in best or offer['conservative_ev'] > best[row[0]][2]['conservative_ev']:
            best[row[0]] = row
    ranked = sorted(best.values(), key=lambda row: row[2]['conservative_ev'], reverse=True)
    kept = ranked[:1]
    for row in ranked[1:policy.max_picks]:
        if row[2]['conservative_ev'] >= policy.second_pick_min_cev:
            kept.append(row)
    return kept


def settle(row, hg, ag):
    market, side, q = row[2]['_settle']
    matrix = point_mass(hg, ag)
    if market == '1x2':
        result = one_x_two(matrix)[side]
    elif market == 'ou':
        result = ou_payout(matrix, side, q)
    else:
        result = ah_payout(matrix, side, q)
    win, loss = win_loss(result)
    return (row[2]['odds'] - 1) * win - loss, result


def closing_value(record, row):
    """Price taken vs. Pinnacle closing no-vig probability (CLV, as EV at close)."""
    odds = record['odds']
    market, side, q = row[2]['_settle']
    if market == '1x2' and odds.get('psc_1x2'):
        p = no_vig(odds['psc_1x2'])[('home', 'draw', 'away').index(side)]
        return row[2]['odds'] * p - 1
    if market == 'ou' and odds.get('psc_ou'):
        p = no_vig(odds['psc_ou'])[0 if side == 'over' else 1]
        return row[2]['odds'] * p - 1
    if market == 'ah' and odds.get('psc_ah') and odds.get('AHCh') == odds.get('AHh') and odds['AHh'] * 4 % 2 == 0:
        # Whole/half lines only: quarter lines need full payout structure.
        p = no_vig(odds['psc_ah'])[0 if side == 'home' else 1]
        return row[2]['odds'] * p - 1
    return None


# ---------------------------------------------------------------------------
# Replay and reporting
# ---------------------------------------------------------------------------

def load_records(path):
    with open(path, encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def replay(records, policy, mode='value'):
    bets = []
    for record in records:
        if not record.get('dc'):
            continue
        market_goals = record.get(f'mg_{policy.goal_book}')
        if market_goals is None and policy.market_weight > 0:
            continue
        home, away = blend(record['dc'][:2], market_goals, policy.market_weight)
        matrix = score_matrix(home, away, 0.0)
        opps = opportunities(record, policy, matrix)
        if not opps:
            continue
        if mode == 'value':
            chosen = value_picks(opps, policy)
        else:
            # select_markets reads gate_reasons and offer keys exactly as live.
            stripped = [(m, l, {k: v for k, v in o.items()}) for m, l, o in opps]
            forecasts, _ = select_markets(stripped)
            chosen = [row for row in forecasts if 'EV_IMPLAUSIBLE' not in row[2]['gate_reasons']]
        for row in chosen:
            profit, result = settle(row, record['hg'], record['ag'])
            bets.append({'season': record['season'], 'code': record['code'], 'kickoff': record['kickoff'],
                         'fixture': (record['code'], record['kickoff'], record['home']),
                         'market': row[0], 'side': row[2]['side'], 'odds': row[2]['odds'],
                         'ev': row[2]['ev'], 'profit': profit,
                         'won': result[0] + result[1] > 0, 'push': result[2] == 1.0,
                         'clv': closing_value(record, row)})
    return bets


def summary(bets, boot=0, seed=11):
    n = len(bets)
    if not n:
        return {'n': 0}
    profit = sum(b['profit'] for b in bets)
    decisive = [b for b in bets if not b['push']]
    clv = [b['clv'] for b in bets if b['clv'] is not None]
    out = {'n': n, 'profit': round(profit, 2), 'roi': round(100 * profit / n, 2),
           'hit': round(100 * sum(b['won'] for b in decisive) / max(len(decisive), 1), 1),
           'avg_odds': round(sum(b['odds'] for b in bets) / n, 3),
           'avg_ev': round(100 * sum(b['ev'] for b in bets) / n, 2),
           'clv': round(100 * sum(clv) / len(clv), 2) if clv else None,
           'clv_pos': round(100 * sum(c > 0 for c in clv) / len(clv), 1) if clv else None}
    if boot:
        by_fixture = defaultdict(list)
        for b in bets:
            by_fixture[b['fixture']].append(b['profit'])
        groups = list(by_fixture.values())
        rng = random.Random(seed)
        rois = []
        for _ in range(boot):
            sample = [groups[rng.randrange(len(groups))] for _ in groups]
            total = sum(sum(g) for g in sample)
            count = sum(len(g) for g in sample)
            rois.append(100 * total / count)
        rois.sort()
        out['roi_ci90'] = (round(rois[int(0.05 * boot)], 2), round(rois[int(0.95 * boot)], 2))
    return out


def fmt(label, s):
    if not s.get('n'):
        return f'{label:44s} n=0'
    ci = f" ci90={s['roi_ci90']}" if 'roi_ci90' in s else ''
    clv = f" clv={s['clv']:+.2f}% (+{s['clv_pos']}%)" if s.get('clv') is not None else ''
    return (f"{label:44s} n={s['n']:5d} hit={s['hit']:5.1f}% odds={s['avg_odds']:.2f} "
            f"claimedEV={s['avg_ev']:+6.2f}% roi={s['roi']:+6.2f}% pnl={s['profit']:+8.2f}{clv}{ci}")


def report(records, policies, mode='value', boot=0, by_market=True):
    results = {}
    for policy in policies:
        bets = replay(records, policy, mode)
        results[policy.name] = bets
        dev = [b for b in bets if b['season'] in DEV_SEASONS]
        test = [b for b in bets if b['season'] in TEST_SEASONS]
        print(fmt(f'{policy.name} [dev]', summary(dev, boot)))
        print(fmt(f'{policy.name} [test]', summary(test, boot)))
        if by_market:
            for market in policy.markets:
                print(fmt(f'   {market} dev', summary([b for b in dev if b['market'] == market])))
                print(fmt(f'   {market} test', summary([b for b in test if b['market'] == market])))
    return results


def evaluate_main(path):
    worst = check_parity()
    print(f'payout parity ok (max abs diff {worst:.1e})')
    records = load_records(path)
    print(f'{len(records)} fixture records, {sum(1 for r in records if r.get("dc"))} with model projection')
    live_v4 = Policy('v4 goal-model blend (retired)')
    # Live v5 proxy: Bet365 pre-match price stands in for 1xbit, Pinnacle
    # pre-match no-vig is the sharp reference; constants match sharp_reference.py.
    sharp_v5 = Policy('v5 sharp reference', goal_book='ps', novig_book='ps', price_book='b365',
                      market_weight=1.0, anchor={'1x2': 0.0, 'ou': 0.0, 'ah': 0.0, 'btts': 0.0},
                      penalty=0.0, ev_gate=0.02, max_gap=1.0, odds_floor=1.30, odds_cap=5.0, ev_cap=0.25)
    print('-- card forecasts (v4)')
    report(records, [live_v4], mode='card', boot=1000)
    print('-- value picks')
    results = report(records, [live_v4, sharp_v5], mode='value', boot=1000)
    for name, bets in results.items():
        for season in ('2223', '2324', '2425', '2526'):
            print(fmt(f'   {name} {season}', summary([b for b in bets if b['season'] == season])))
