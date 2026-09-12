"""Offline four-market calculator; produces projections only and writes nothing."""
import argparse
from dataclasses import asdict
import json
import math

from .markets import asian_handicap, btts, match_odds, over_under
from .score_matrix import build_score_matrix
from .value import expected_value, fair_odds


def view(payout, odds=None):
    result = asdict(payout)
    result['fair_odds'] = fair_odds(payout)
    result['ev'] = expected_value(payout, odds) if odds is not None else None
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lambda-home', type=float, required=True)
    parser.add_argument('--lambda-away', type=float, required=True)
    parser.add_argument('--rho', type=float, default=0.0)
    parser.add_argument('--ou-line', type=float, default=2.5)
    parser.add_argument('--ah-line', type=float, default=0.0)
    parser.add_argument('--odds-json', default='{}', help='Optional JSON map, e.g. {"1x2.home":2.4,"ou.over":1.95}')
    args = parser.parse_args(argv)
    ou_quarters, ah_quarters = round(args.ou_line * 4), round(args.ah_line * 4)
    if abs(ou_quarters - args.ou_line * 4) > 1e-8 or abs(ah_quarters - args.ah_line * 4) > 1e-8:
        parser.error('Lines must use quarter-goal increments')
    try:
        odds = json.loads(args.odds_json, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        if type(odds) is not dict:
            raise ValueError('odds JSON must be an object')
        allowed = {f'{market}.{side}' for market, sides in {
            '1x2': ('home', 'draw', 'away'), 'btts': ('yes', 'no'),
            'ou': ('over', 'under'), 'ah': ('home', 'away')}.items() for side in sides}
        if not set(odds).issubset(allowed):
            raise ValueError('unknown odds key')
        if any(type(price) not in (int, float) or not math.isfinite(price) or price <= 1 for price in odds.values()):
            raise ValueError('invalid decimal odds')
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        parser.error(f'invalid --odds-json: {exc}')
    distribution = build_score_matrix(args.lambda_home, args.lambda_away, args.rho)
    one_x_two, both = match_odds(distribution), btts(distribution)
    result = {
        'status': 'projection_only', 'official_enabled': False,
        'matrix': {'max_goals': distribution.max_goals, 'raw_mass': distribution.raw_mass,
                   'tail_mass_bound': distribution.tail_mass_bound},
        '1x2': {side: view(value, odds.get(f'1x2.{side}')) for side, value in one_x_two.items()},
        'btts': {side: view(value, odds.get(f'btts.{side}')) for side, value in both.items()},
        'ou': {side: view(over_under(distribution, side, ou_quarters), odds.get(f'ou.{side}')) for side in ('over', 'under')},
        'ah': {side: view(asian_handicap(distribution, side, ah_quarters if side == 'home' else -ah_quarters), odds.get(f'ah.{side}'))
               for side in ('home', 'away')},
    }
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
