"""Standalone cup / no-model fixture analyzer.

This is deliberately separate from the production gate. It exists for exactly
one situation: a live fixture that the production Dixon-Coles model cannot
project - cup ties, lower-tier teams, cross-league meetings - where the old
behaviour was to silently produce nothing at all.

Decision ladder (highest priority first)
----------------------------------------
1. production model projection, when the caller supplies a valid artifact
2. historical strength rating, when both teams have multi-season history
3. competition prior, when the competition itself has history but the teams
   do not (e.g. a cup tie between two obscure clubs)
4. market-only, when no model basis exists - the market is priced directly and
   every output is labelled ``market_only``

Output contract
---------------
The analyzer never writes to picks.json, bets.db, or any settlement state. It
emits at most one card per market family (AH, O/U, BTTS, 1X2) per fixture, and
only one AH side, one O/U direction and one BTTS direction, as the compact
card requires. Odds are never invented: missing odds or lines surface as null
and the card reports that the market is unavailable.
"""
import json
import math
import os
import sys
import time
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FC_DIR = os.path.join(BASE_DIR, 'betting-machine-fc')
if not os.path.isdir(os.path.join(FC_DIR, 'data')):
    # Allow running from the repo root or the scripts directory.
    FC_DIR = os.path.dirname(os.path.abspath(__file__))
    while FC_DIR and not os.path.isdir(os.path.join(FC_DIR, 'betting-machine-fc')):
        parent = os.path.dirname(FC_DIR)
        if parent == FC_DIR:
            break
        FC_DIR = parent
    FC_DIR = os.path.join(FC_DIR, 'betting-machine-fc')
sys.path.insert(0, FC_DIR)

from football_formula_engine.historical_store import HistoricalStore  # noqa: E402
from football_formula_engine.strength import TeamStrength  # noqa: E402

CUP_LEAGUE_TOKENS = (
    'fa cup', 'cup', 'beker', 'copa', 'pokal', 'coupe', 'knvb', 'emperors',
    'league cup', 'carabao', 'super cup', 'cup uefa', 'cup. women',
)
NEUTRAL_TOKENS = ('semi-final', 'final', 'wembley', 'neutral')
STRENGTH_LADDER = ('production', 'fc-historical-strength-v1', 'competition-prior', 'market-only')
CARD_VERSION = 'fc-cup-research-v1'
RESEARCH_ARTIFACT = os.path.join(FC_DIR, 'data', 'cup_research.json')
ANALYZER_VERSION = 'fc-cup-analyzer-v1'
MIN_HISTORY_MATCHES = 8
ODDS_FLOOR = 1.6
ODDS_CAP = 2.5


def log(msg):
    print(msg, file=sys.stderr)


def season_order(season):
    try:
        return int(season)
    except ValueError:
        return 0


def is_cup_fixture(league_name):
    league = (league_name or '').lower()
    return any(token in league for token in CUP_LEAGUE_TOKENS)


def is_neutral_round(league_name, round_label=''):
    text = f'{league_name} {round_label}'.lower()
    return any(token in text for token in NEUTRAL_TOKENS)


def normalise_name(name):
    return ' '.join((name or '').lower().replace('-', ' ').replace('.', '').split())


class CupAnalyzer:
    """Read-only analysis of fixtures the production model cannot cover."""

    def __init__(self, data_dir=None):
        self.data_dir = data_dir or os.path.join(FC_DIR, 'data')
        self.store = HistoricalStore(self.data_dir)
        self.strength = None

    # ------------------------------------------------------------------ fit
    def fit(self):
        self.strength = TeamStrength(self.store).fit()
        log(f'[cup-analyzer] historical store: {len(self.store.results)} results, '
            f'{len(self.strength.known_teams())} rated teams, '
            f'{len(self.strength.competitions)} competitions')
        return self

    # ------------------------------------------------------- market pricing
    @staticmethod
    def _no_vig(odds_list):
        inv = sum(1.0 / o for o in odds_list if o and o > 1)
        if inv <= 0:
            return [None] * len(odds_list)
        return [round((1.0 / o) / inv, 4) if o and o > 1 else None for o in odds_list]

    def _market_cards(self, mk):
        """Price whatever the market actually quotes. Nothing is invented."""
        cards = []

        one_x_two = {int(k): v for k, v in (mk.get('odds_1x2') or {}).items()
                     if str(k) in ('1', '2', '3')}
        if all(t in one_x_two for t in (1, 2, 3)):
            probs = self._no_vig([one_x_two[1], one_x_two[2], one_x_two[3]])
            for tag, side, prob in (('1', 'home', probs[0]), ('2', 'draw', probs[1]),
                                    ('3', 'away', probs[2])):
                odds = one_x_two[int(tag)]
                if ODDS_FLOOR <= odds <= ODDS_CAP and prob:
                    cards.append({'market': '1x2', 'side': side, 'line': None,
                                  'odds': odds, 'model_prob': prob, 'source': 'market'})

        btts = mk.get('odds_btts') or {}
        if 'yes' in btts and 'no' in btts:
            probs = self._no_vig([btts['yes'], btts['no']])
            for side, prob in (('yes', probs[0]), ('no', probs[1])):
                odds = btts[side]
                if ODDS_FLOOR <= odds <= ODDS_CAP and prob:
                    cards.append({'market': 'btts', 'side': side, 'line': None,
                                  'odds': odds, 'model_prob': prob, 'source': 'market'})

        for line, sides in (mk.get('odds_ou') or {}).items():
            sides = {str(k): v for k, v in sides.items()}
            if '9' not in sides or '10' not in sides:
                continue
            probs = self._no_vig([sides['9'], sides['10']])
            for side, key, prob in (('over', '9', probs[0]), ('under', '10', probs[1])):
                odds = sides[key]
                if ODDS_FLOOR <= odds <= ODDS_CAP and prob:
                    cards.append({'market': 'ou', 'side': side, 'line': float(line),
                                  'odds': odds, 'model_prob': prob, 'source': 'market'})

        by_line = {}
        for price, odds in (mk.get('odds_ah') or {}).get('home') or []:
            try:
                by_line.setdefault(float(price), {})['home'] = float(odds)
            except (TypeError, ValueError):
                continue
        for price, odds in (mk.get('odds_ah') or {}).get('away') or []:
            try:
                by_line.setdefault(-float(price), {})['away'] = float(odds)
            except (TypeError, ValueError):
                continue
        for line, sides in by_line.items():
            if 'home' not in sides or 'away' not in sides:
                continue
            probs = self._no_vig([sides['home'], sides['away']])
            for side, prob, odds in (('home', probs[0], sides['home']),
                                     ('away', probs[1], sides['away'])):
                if ODDS_FLOOR <= odds <= ODDS_CAP and prob:
                    cards.append({'market': 'ah', 'side': side, 'line': line,
                                  'odds': odds, 'model_prob': prob, 'source': 'market'})
        return cards

    def _model_cards(self, distribution, mk):
        """Price the same markets with a fitted distribution."""
        from football_formula_engine.markets import asian_handicap, btts, match_odds, over_under
        from football_formula_engine.value import expected_value, fair_odds
        cards = []

        def add(market, side, line, payout, odds, model_prob):
            if not (ODDS_FLOOR <= odds <= ODDS_CAP):
                return None
            ev = expected_value(payout, odds)
            return {'market': market, 'side': side, 'line': line, 'odds': odds,
                    'model_prob': round(model_prob, 4),
                    'effective_win_prob': round(payout.full_win + 0.5 * payout.half_win, 4),
                    'ev': round(ev, 4), 'fair_odds': round(fair_odds(payout), 3),
                    'source': 'model'}

        one_x_two = {int(k): v for k, v in (mk.get('odds_1x2') or {}).items()
                     if str(k) in ('1', '2', '3')}
        if all(t in one_x_two for t in (1, 2, 3)):
            payouts = match_odds(distribution)
            for tag, side in (('1', 'home'), ('2', 'draw'), ('3', 'away')):
                card = add('1x2', side, None, payouts[side], one_x_two[int(tag)],
                           payouts[side].full_win + 0.5 * payouts[side].half_win)
                if card:
                    cards.append(card)
        b = mk.get('odds_btts') or {}
        if 'yes' in b and 'no' in b:
            payouts = btts(distribution)
            for side in ('yes', 'no'):
                card = add('btts', side, None, payouts[side], b[side],
                           payouts[side].full_win + 0.5 * payouts[side].half_win)
                if card:
                    cards.append(card)
        for line, sides in (mk.get('odds_ou') or {}).items():
            sides = {str(k): v for k, v in sides.items()}
            try:
                line_value = float(line)
            except (TypeError, ValueError):
                continue
            quarters = round(line_value * 4)
            if abs(line_value * 4 - quarters) > 1e-8 or '9' not in sides or '10' not in sides:
                continue
            for side, key in (('over', '9'), ('under', '10')):
                try:
                    payout = over_under(distribution, side, quarters)
                except Exception:
                    continue
                card = add('ou', side, line_value, payout, sides[key],
                           payout.full_win + 0.5 * payout.half_win)
                if card:
                    cards.append(card)
        by_line = {}
        for price, odds in (mk.get('odds_ah') or {}).get('home') or []:
            try:
                by_line.setdefault(float(price), {})['home'] = float(odds)
            except (TypeError, ValueError):
                continue
        for price, odds in (mk.get('odds_ah') or {}).get('away') or []:
            try:
                by_line.setdefault(-float(price), {})['away'] = float(odds)
            except (TypeError, ValueError):
                continue
        for line, sides in by_line.items():
            if 'home' not in sides or 'away' not in sides:
                continue
            quarters = round(line * 4)
            if abs(line * 4 - quarters) > 1e-8:
                continue
            for side in ('home', 'away'):
                signed = quarters if side == 'home' else -quarters
                try:
                    payout = asian_handicap(distribution, side, signed)
                except Exception:
                    continue
                card = add('ah', side, line, payout, sides[side],
                           payout.full_win + 0.5 * payout.half_win)
                if card:
                    cards.append(card)
        return cards

    # --------------------------------------------------------------- analyse
    def analyse(self, info, mk, *, production_projection=None):
        """Build one compact card for a fixture.

        ``production_projection`` may carry a ``distribution`` from the real
        Dixon-Coles model. When present and valid it wins outright.
        """
        home = info.get('home')
        away = info.get('away')
        league = info.get('league') or ''
        coverage = 'market_only'
        rating_basis = None
        reasons = []
        distribution = None
        est = None

        if production_projection is not None and production_projection.get('distribution'):
            distribution = production_projection['distribution']
            coverage = 'full'
            rating_basis = 'production-dixon-coles'
        else:
            home_stored = self.store.resolve_team(home)
            away_stored = self.store.resolve_team(away)
            est = (self.strength.lambdas(home_stored, away_stored)
                   if home_stored and away_stored else None)
            if est is not None:
                distribution = _build_distribution(est['lambda_home'], est['lambda_away'])
                coverage = 'rated'
                rating_basis = est['rating_source']
                if est['home_matches'] < MIN_HISTORY_MATCHES:
                    reasons.append('HOME_TEAM_THIN_HISTORY')
                if est['away_matches'] < MIN_HISTORY_MATCHES:
                    reasons.append('AWAY_TEAM_THIN_HISTORY')
            else:
                reasons.append('NO_TEAM_HISTORY_FALLBACK_TO_MARKET')
                if home_stored is None:
                    reasons.append('HOME_TEAM_UNRESOLVED')
                if away_stored is None:
                    reasons.append('AWAY_TEAM_UNRESOLVED')
                home_cov = self.store.coverage(home_stored or '')
                away_cov = self.store.coverage(away_stored or '')
                if not home_cov and not away_cov:
                    reasons.append('BOTH_TEAMS_UNKNOWN_TO_STORE')

        if distribution is None:
            cards = self._market_cards(mk)
        else:
            cards = self._model_cards(distribution, mk)

        # Compact card: one AH side, one O/U direction, one BTTS direction.
        compact = _compact_card(cards)

        expected_goals = {'home': None, 'away': None}
        if est is not None:
            expected_goals = {'home': est['lambda_home'], 'away': est['lambda_away']}
        elif production_projection is not None:
            expected_goals = {'home': production_projection.get('lambda_home'),
                              'away': production_projection.get('lambda_away')}

        return {
            'analyzer_version': ANALYZER_VERSION,
            'generated_at': datetime.now(tz=timezone.utc).isoformat(),
            'match_id': str(info.get('match_id') or ''),
            'home': home,
            'away': away,
            'league': league,
            'start_ts': int(float(info.get('start_ts') or 0)),
            'is_cup': is_cup_fixture(league),
            'is_neutral_venue': is_neutral_round(league),
            'coverage_status': coverage,
            'rating_basis': rating_basis,
            'model_source': rating_basis or 'market-only',
            'confidence': _confidence(coverage, reasons),
            'decision': 'watch',
            'reason_codes': reasons,
            'expected_goals': expected_goals,
            'card': compact,
            'all_priced': cards,
            'market_availability': _market_availability(mk),
            'official_eligible': False,
            'note': 'Standalone research output. Not the production gate; '
                    'do not treat as an official pick.',
        }


def _build_distribution(lambda_home, lambda_away, rho=0.0, max_goals=12):
    from football_formula_engine.score_matrix import build_score_matrix
    return build_score_matrix(lambda_home, lambda_away, rho)


def _confidence(coverage, reasons):
    if coverage == 'full':
        return 'medium' if reasons else 'high'
    if coverage == 'rated':
        return 'low' if any('THIN' in r for r in reasons) else 'medium'
    return 'low'


def _market_availability(mk):
    one_x_two = {str(k): v for k, v in (mk.get('odds_1x2') or {}).items()}
    btts = mk.get('odds_btts') or {}
    ou_lines = list((mk.get('odds_ou') or {}).keys())
    ah_home = (mk.get('odds_ah') or {}).get('home') or []
    return {
        '1x2': all(t in one_x_two for t in ('1', '2', '3')),
        'btts': bool(btts.get('yes') and btts.get('no')),
        'ou_lines': [float(line) for line in ou_lines],
        'ah_lines': sorted({abs(float(p)) for p, _ in ah_home if _is_num(p)}),
    }


def _is_num(value):
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _compact_card(cards):
    """Reduce the priced set to the compact card shape.

    One AH side, one O/U direction, one BTTS direction. Within a market family
    the selection is by expected value when available, otherwise by model
    probability, so the card shows the strongest single option rather than a
    full price list.
    """
    if not cards:
        return {'ah': None, 'ou': None, 'btts': None, '1x2': None}

    def score(card):
        return card.get('ev') if card.get('ev') is not None else 0.0

    by_market = {}
    for card in cards:
        by_market.setdefault(card['market'], []).append(card)

    def best(market, line_key='line'):
        rows = by_market.get(market) or []
        if not rows:
            return None
        return max(rows, key=lambda row: (score(row), row.get('model_prob') or 0))

    def best_sided(market):
        rows = by_market.get(market) or []
        if not rows:
            return None
        by_line = {}
        for row in rows:
            key = row.get('line')
            by_line.setdefault(key, []).append(row)
        options = []
        for line, group in by_line.items():
            top = max(group, key=lambda row: (score(row), row.get('model_prob') or 0))
            options.append(top)
        return max(options, key=lambda row: (score(row), row.get('model_prob') or 0))

    return {
        'ah': best_sided('ah'),
        'ou': best_sided('ou'),
        'btts': best('btts'),
        '1x2': best('1x2'),
    }


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', nargs=2, metavar=('HOME', 'AWAY'),
                        help='analyse a single offline fixture (no live odds)')
    parser.add_argument('--live', action='store_true',
                        help='analyse live 1xbit fixtures and write the read-only research artifact')
    parser.add_argument('--max', type=int, default=40,
                        help='maximum number of live fixtures to analyse with --live')
    args = parser.parse_args(argv)

    analyzer = CupAnalyzer().fit()
    print(json.dumps({'competitions': analyzer.store.competition_summary(),
                      'rated_teams': len(analyzer.strength.known_teams())},
                     indent=2, sort_keys=True))
    if args.fixture:
        est = analyzer.strength.lambdas(normalise_name(args.fixture[0]),
                                        normalise_name(args.fixture[1]))
        print(json.dumps({'fixture': args.fixture, 'lambdas': est},
                         indent=2, sort_keys=True))
        return 0
    if args.live:
        return run_live(analyzer, args.max)
    return 0


def run_live(analyzer, max_fixtures):
    """Analyse live 1xbit fixtures and write the standalone research artifact.

    Read-only with respect to the production pipeline: nothing is written to
    picks.json, bets.db or the settlement layer. cup_research.json is a
    separate file the dashboard may read as a research surface.
    """
    import scraper_1xbit as sc  # noqa: E402

    rows = sc.list_matches_paginated(window_hours=96, max_pages=10)
    print('live fixtures:', len(rows))

    results = []
    for row in rows[:max_fixtures]:
        info = {'match_id': row.get('I'), 'home': row.get('O1'), 'away': row.get('O2'),
                'league': row.get('L'), 'start_ts': float(row.get('S') or 0)}
        try:
            detail = sc.get_match(row.get('I'))
            markets = sc.extract_markets(detail)
        except Exception as exc:
            print('quote fail', row.get('I'), exc)
            continue
        results.append(analyzer.analyse(info, markets))

    payload = {
        'card_version': CARD_VERSION,
        'analyzer_version': ANALYZER_VERSION,
        'generated_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        'fixture_source': '1xbit-live',
        'fallback_ladder': STRENGTH_LADDER,
        'official_enabled': False,
        'official_reason': 'MODEL_NOT_VALIDATED',
        'note': 'Standalone research output. Not the production gate; not an official pick.',
        'matches': results,
    }
    os.makedirs(os.path.dirname(RESEARCH_ARTIFACT), exist_ok=True)
    with open(RESEARCH_ARTIFACT, 'w') as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)
    by_cov = {}
    for item in results:
        by_cov[item['coverage_status']] = by_cov.get(item['coverage_status'], 0) + 1
    print('wrote', RESEARCH_ARTIFACT)
    print('analysed', len(results), 'coverage', by_cov)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
