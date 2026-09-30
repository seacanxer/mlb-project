"""Research projections for corners and cards from real match-stat CSV rows.

Missing inputs stay missing. This module never makes up bookmaker prices and
its projections are not value picks or approved staking signals.
"""
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import nbinom, poisson


DEFAULT_CONFIG = {
    'version': 'fc-secondary-counts-v1',
    'half_life_team_matches': 8.0,
    'pseudo_matches': 8.0,
    'minimum_effective_team_side': 3.0,
    'minimum_effective_league': 30.0,
    'minimum_referee_matches': 3,
    'yellow_points': 1,
    'red_points': 2,
    'dispersion_min': 2.0,
    'dispersion_max': 100.0,
    'dominance_log_slope': 0.035,
    'dominance_clip': 2.0,
    'probability_tail': 1e-9,
}
CONFIG_PATH = Path(__file__).resolve().parents[1] / 'config-secondary-markets.json'


def load_config(path=CONFIG_PATH):
    config = dict(DEFAULT_CONFIG)
    try:
        override = json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return config
    if type(override) is not dict or set(override) - set(config):
        raise ValueError('Invalid secondary-market model config keys')
    config.update(override)
    for key, value in config.items():
        if key == 'version' and type(value) is str and value:
            continue
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f'Invalid secondary-market model config: {key}')
    if config['half_life_team_matches'] <= 0 or config['pseudo_matches'] < 0:
        raise ValueError('Invalid secondary-market shrinkage config')
    if not 0 < config['probability_tail'] < .01:
        raise ValueError('Invalid probability tail config')
    return config


CONFIG = load_config()


def _number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (TypeError, ValueError):
        return None


def _date(value):
    value = (value or '').strip()
    for fmt in ('%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def load_stat_rows(paths):
    """Read actual football-data statistics; unavailable fields remain None."""
    rows, seen = [], set()
    for path in paths:
        path = Path(path)
        if not path.exists():
            continue
        try:
            with path.open(newline='', encoding='utf-8-sig') as handle:
                for raw in csv.DictReader(handle):
                    day = _date(raw.get('Date'))
                    home, away = (raw.get('HomeTeam') or '').strip(), (raw.get('AwayTeam') or '').strip()
                    if not day or not home or not away:
                        continue
                    identity = (day, home, away)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    rows.append({
                        'date': day, 'home': home, 'away': away,
                        'home_goals': _number(raw.get('FTHG')),
                        'away_goals': _number(raw.get('FTAG')),
                        'home_corners': _number(raw.get('HC')),
                        'away_corners': _number(raw.get('AC')),
                        'home_yellow': _number(raw.get('HY')),
                        'away_yellow': _number(raw.get('AY')),
                        'home_red': _number(raw.get('HR')),
                        'away_red': _number(raw.get('AR')),
                        'home_fouls': _number(raw.get('HF')),
                        'away_fouls': _number(raw.get('AF')),
                        'referee': (raw.get('Referee') or '').strip() or None,
                    })
        except (OSError, UnicodeError, csv.Error):
            continue
    return sorted(rows, key=lambda row: (row['date'], row['home'], row['away']))


def effective_sample(weights):
    total = float(sum(weights))
    squares = float(sum(weight * weight for weight in weights))
    return total * total / squares if squares else 0.0


def _dispersion(values):
    if len(values) < 2:
        return None
    mean = float(np.mean(values))
    variance = float(np.var(values, ddof=1))
    # Estimate NB size by method of moments. Large values approach Poisson;
    # the distribution remains negative-binomial for count markets.
    return min(CONFIG['dispersion_max'], max(CONFIG['dispersion_min'],
               mean * mean / max(variance - mean, mean * mean / CONFIG['dispersion_max'])))


def _nb(mean, size, tail):
    if mean <= 0:
        return np.asarray([1.0])
    p = size / (size + mean)
    limit = max(12, int(nbinom.ppf(1 - tail, size, p)))
    x = np.arange(limit + 1)
    return nbinom.pmf(x, size, p)


def _poisson(mean, tail):
    limit = max(8, int(poisson.ppf(1 - tail, mean)))
    return poisson.pmf(np.arange(limit + 1), mean)


def _normalize(values):
    total = float(np.sum(values))
    return values / total if total > 0 else values


def _payout(distribution, line, side):
    parts = (line - 0.25, line + 0.25) if abs(line * 2 - round(line * 2)) > 1e-8 else (line, line)
    outcomes = np.zeros(5, dtype=float)  # full-win, half-win, push, half-loss, full-loss
    for value, probability in enumerate(distribution):
        component = []
        for part in parts:
            if side == 'over':
                margin = value - part
            elif side == 'under':
                margin = part - value
            elif side == 'home':
                margin = value + part
            elif side == 'away':
                margin = part - value
            else:
                raise ValueError(f'unsupported settlement side: {side}')
            component.append('win' if margin > 1e-9 else 'loss' if margin < -1e-9 else 'push')
        if component == ['win', 'win']: outcomes[0] += probability
        elif 'win' in component and 'push' in component: outcomes[1] += probability
        elif component == ['push', 'push']: outcomes[2] += probability
        elif 'loss' in component and 'push' in component: outcomes[3] += probability
        else: outcomes[4] += probability
    return {'full_win': outcomes[0], 'half_win': outcomes[1], 'push': outcomes[2],
            'half_loss': outcomes[3], 'full_loss': outcomes[4]}


def _best_total(distribution, mean, market, *, minimum=0.5):
    center = max(minimum, math.floor(mean * 2) / 2)
    candidates = [center + offset * 0.25 for offset in (-4, -3, -2, -1, 0, 1, 2, 3, 4)]
    choices = []
    for line in candidates:
        for side in ('over', 'under'):
            payout = _payout(distribution, line, side)
            win_probability = payout['full_win'] + payout['half_win']
            choices.append({'market': market, 'side': side, 'line': line,
                            'pick': f'{side.title()} {line:g}',
                            'probability': win_probability, 'odds': None,
                            'p_market_novig': None, 'edge': None,
                            'payout': payout, 'availability': 'B',
                            'status': 'projection', 'label': 'Proyeksi',
                            'model_version': CONFIG['version']})
    # Show the central line and the more probable side; avoid shopping a noisy
    # tail line whose probability merely looks high.
    at_center = [row for row in choices if abs(row['line'] - center) <= .25]
    return max(at_center, key=lambda row: (row['probability'], abs(row['line'] - center),
                                            row['side'] == 'under'))


def _best_corner_handicap(home_distribution, away_distribution, home, away,
                          expected_difference):
    difference = np.convolve(home_distribution, away_distribution[::-1])
    offset = len(away_distribution) - 1
    fair_home_line = round(-expected_difference * 4) / 4
    candidates = []
    for line in (fair_home_line, fair_home_line - .25, fair_home_line + .25):
        for side in ('home', 'away'):
            adjusted = line if side == 'home' else -line
            shifted_line = adjusted - offset if side == 'home' else adjusted + offset
            p = _payout(difference, shifted_line, side)
            probability = p['full_win'] + p['half_win']
            name = home if side == 'home' else away
            candidates.append({'market': 'corner_hdp', 'side': side,
                'line': adjusted, 'pick': f'{name} {adjusted:+g}',
                'probability': probability, 'odds': None, 'p_market_novig': None,
                'edge': None, 'payout': p, 'availability': 'B',
                'status': 'projection', 'label': 'Proyeksi',
                'model_version': CONFIG['version']})
    at_center = [row for row in candidates if row['line'] in (fair_home_line, -fair_home_line)]
    return max(at_center or candidates, key=lambda row: row['probability'])


def project_fixture(rows, home, away, kickoff_utc, *, goal_projection=None,
                    referee=None, config=None):
    """Return secondary-market predictions or explicit C/unavailable states."""
    cfg = load_config()
    if config:
        cfg.update(config)
    cutoff_date = datetime.fromtimestamp(float(kickoff_utc), timezone.utc).date()
    eligible = [row for row in rows if row['date'] < cutoff_date and row.get('home_goals') is not None
                and row.get('away_goals') is not None]
    if not eligible:
        return {'availability': 'C', 'reason': 'NO_HISTORICAL_MATCH_STATS', 'markets': [], 'limited': True}

    corner_rows = [r for r in eligible if r['home_corners'] is not None and r['away_corners'] is not None]
    card_rows = [r for r in eligible if r['home_yellow'] is not None and r['away_yellow'] is not None]
    result = {'availability': 'C', 'reason': None, 'markets': [], 'limited': False,
              'referee': referee, 'referee_status': 'unknown' if not referee else 'named',
              'model_version': cfg['version'], 'market_odds_available': False}

    def project_count(rows_for_market, stat, for_key, against_key, label):
        appearances = {}
        ages = [0] * len(rows_for_market)
        for index in range(len(rows_for_market) - 1, -1, -1):
            row = rows_for_market[index]
            ages[index] = appearances.get(row['home'], 0) + appearances.get(row['away'], 0)
            appearances[row['home']] = appearances.get(row['home'], 0) + 1
            appearances[row['away']] = appearances.get(row['away'], 0) + 1
        observations = []
        for row, age in zip(rows_for_market, ages):
            weight = 2 ** (-age / cfg['half_life_team_matches'])
            observations.append((row, weight))
        league_eff = effective_sample([w for _, w in observations])
        if league_eff < cfg['minimum_effective_league']:
            return None
        global_home = sum(row[for_key] * w for row, w in observations) / sum(w for _, w in observations)
        away_for_key = 'away_' + stat
        global_away = sum(row[away_for_key] * w for row, w in observations) / sum(w for _, w in observations)
        team_rows = {'home': [], 'away': []}
        for row, weight in observations:
            team_rows['home'].append((row['home'], row[for_key], row[against_key], weight))
            team_rows['away'].append((row['away'], row[away_for_key], row['home_' + stat], weight))

        def attack_defense(team, role, baseline):
            selected = [entry for entry in team_rows[role] if entry[0] == team]
            n_eff = effective_sample([entry[3] for entry in selected])
            if n_eff < cfg['minimum_effective_team_side']:
                return None, n_eff
            weight_sum = sum(entry[3] for entry in selected)
            scored = sum(entry[1] * entry[3] for entry in selected)
            conceded = sum(entry[2] * entry[3] for entry in selected)
            pseudo = cfg['pseudo_matches']
            attack = (scored + pseudo * baseline) / (weight_sum + pseudo) / baseline
            defense = (conceded + pseudo * baseline) / (weight_sum + pseudo) / baseline
            return (attack, defense), n_eff

        home_strength, home_n = attack_defense(home, 'home', global_home)
        away_strength, away_n = attack_defense(away, 'away', global_away)
        if not home_strength or not away_strength:
            return None
        dominance = 0.0
        if goal_projection and all(goal_projection.get(k) is not None for k in ('home', 'away')):
            dominance = max(-cfg['dominance_clip'], min(cfg['dominance_clip'],
                goal_projection['home'] - goal_projection['away']))
        modifier = math.exp(cfg['dominance_log_slope'] * dominance)
        home_mean = global_home * home_strength[0] * away_strength[1] * modifier
        away_mean = global_away * away_strength[0] * home_strength[1] / modifier
        dispersion = _dispersion([row[for_key] for row, _ in observations]
                                 + [row[away_for_key] for row, _ in observations])
        if label == 'corners':
            dist_home = _nb(home_mean, dispersion, cfg['probability_tail'])
            dist_away = _nb(away_mean, dispersion, cfg['probability_tail'])
            total = _normalize(np.convolve(dist_home, dist_away))
            total_mean = home_mean + away_mean
            return {'home': home_mean, 'away': away_mean, 'total': total_mean,
                    'home_distribution': dist_home, 'away_distribution': dist_away,
                    'distribution': total, 'dispersion': dispersion,
                    'n_eff': min(home_n, away_n), 'team_home_n_eff': home_n,
                    'team_away_n_eff': away_n, 'referee_status': 'not_applicable'}
        # Yellow-card points plus an independent low-rate red-card process.
        reds = [row['home_red'] + row['away_red'] for row, _ in observations
                if row['home_red'] is not None and row['away_red'] is not None]
        red_mean = float(np.mean(reds)) if reds else 0.0
        red_home = float(np.mean([r['home_red'] for r, _ in observations if r['home_red'] is not None])) if reds else 0.0
        red_away = float(np.mean([r['away_red'] for r, _ in observations if r['away_red'] is not None])) if reds else 0.0
        ref_rows = []
        if referee:
            ref_rows = [row for row, _ in observations if row.get('referee') == referee]
            if len(ref_rows) >= cfg['minimum_referee_matches']:
                referee_yellows = sum((r['home_yellow'] or 0) + (r['away_yellow'] or 0)
                                      for r in ref_rows) / len(ref_rows)
                league_yellows = sum((r['home_yellow'] or 0) + (r['away_yellow'] or 0)
                                     for r, _ in observations) / len(observations)
                shrunk_referee_rate = (referee_yellows * len(ref_rows)
                    + cfg['pseudo_matches'] * league_yellows) / (len(ref_rows) + cfg['pseudo_matches'])
                ref_factor = shrunk_referee_rate / league_yellows if league_yellows else 1.0
                home_mean *= ref_factor
                away_mean *= ref_factor
                yellow_mean = home_mean + away_mean
                referee_reds = sum((r['home_red'] or 0) + (r['away_red'] or 0)
                                   for r in ref_rows) / len(ref_rows)
                red_mean = ((referee_reds * len(ref_rows) + cfg['pseudo_matches'] * red_mean)
                            / (len(ref_rows) + cfg['pseudo_matches']))
                red_home = red_mean * (red_home / (red_home + red_away)) if red_home + red_away else red_mean / 2
                red_away = red_mean - red_home
        yellow_mean = home_mean + away_mean
        size = dispersion if referee and len(ref_rows) >= cfg['minimum_referee_matches'] else max(cfg['dispersion_min'], dispersion * 0.5)
        yellow_dist = _nb(yellow_mean, size, cfg['probability_tail'])
        red_dist = _poisson(red_mean, cfg['probability_tail'])
        shifted = np.zeros(len(yellow_dist) + max(0, (len(red_dist) - 1) * cfg['red_points']))
        for red_count, probability in enumerate(red_dist):
            start = red_count * cfg['red_points']
            shifted[start:start + len(yellow_dist)] += probability * yellow_dist
        shifted = _normalize(shifted)
        home_yellow = _nb(home_mean, size, cfg['probability_tail'])
        away_yellow = _nb(away_mean, size, cfg['probability_tail'])
        red_home_dist = _poisson(red_home, cfg['probability_tail'])
        red_away_dist = _poisson(red_away, cfg['probability_tail'])
        def points(yellows, reds):
            out = np.zeros(len(yellows) + max(0, (len(reds) - 1) * cfg['red_points']))
            for red_count, probability in enumerate(reds):
                start = red_count * cfg['red_points']
                out[start:start + len(yellows)] += probability * yellows
            return _normalize(out)
        return {'home': home_mean, 'away': away_mean,
                'home_points': home_mean * cfg['yellow_points'] + red_home * cfg['red_points'],
                'away_points': away_mean * cfg['yellow_points'] + red_away * cfg['red_points'],
                'total': yellow_mean * cfg['yellow_points'] + red_mean * cfg['red_points'],
                'distribution': shifted, 'dispersion': dispersion,
                'home_distribution': points(home_yellow, red_home_dist),
                'away_distribution': points(away_yellow, red_away_dist),
                'red_yes_probability': 1 - math.exp(-red_mean),
                'red_mean': red_mean, 'yellow_mean': yellow_mean,
                'n_eff': min(home_n, away_n), 'team_home_n_eff': home_n,
                'team_away_n_eff': away_n,
                'referee_status': 'used' if referee and len(ref_rows) >= cfg['minimum_referee_matches'] else 'unknown'}

    corner = project_count(corner_rows, 'corners', 'home_corners', 'away_corners', 'corners') if corner_rows else None
    cards = project_count(card_rows, 'yellow', 'home_yellow', 'away_yellow', 'cards') if card_rows else None
    if corner:
        result['corners'] = {key: value for key, value in corner.items() if 'distribution' not in key}
        result['markets'].append(_best_total(corner['distribution'], corner['total'], 'corners_ou'))
        result['markets'].append(_best_corner_handicap(corner['home_distribution'],
            corner['away_distribution'], home, away, corner['home'] - corner['away']))
    if cards:
        result['cards'] = {key: value for key, value in cards.items() if 'distribution' not in key}
        result['markets'].append(_best_total(cards['distribution'], cards['total'], 'cards_ou'))
        team_options = []
        for name, side, mean in ((home, 'home', cards['home_points']), (away, 'away', cards['away_points'])):
            projection = _best_total(cards[f'{side}_distribution'], mean, 'team_cards_ou')
            projection['pick'] = f'{name} {projection["pick"]}'
            projection['team'] = side
            team_options.append(projection)
        result['markets'].append(max(team_options, key=lambda row: row['probability']))
        result['referee_status'] = cards['referee_status']
        if cards['red_mean'] > 0:
            yes_probability = cards['red_yes_probability']
            result['markets'].append({'market': 'red_card', 'side': 'yes' if yes_probability >= .5 else 'no',
                'line': None, 'pick': 'Red card yes' if yes_probability >= .5 else 'Red card no',
                'probability': max(yes_probability, 1 - yes_probability), 'odds': None,
                'p_market_novig': None, 'edge': None, 'availability': 'B',
                'status': 'projection', 'label': 'Proyeksi', 'model_version': cfg['version']})
    result['availability'] = 'B' if result['markets'] else 'C'
    result['limited'] = result['availability'] == 'B'
    if not result['markets']:
        result['reason'] = 'INSUFFICIENT_EFFECTIVE_MATCH_STATS'
    return result
