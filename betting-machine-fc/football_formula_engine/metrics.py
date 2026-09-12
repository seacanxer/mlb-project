"""Proper scoring and reliability metrics for chronological FC evaluation."""
import math

from .contracts import require


EPSILON = 1e-15


def _clip(probability):
    require(type(probability) in (int, float) and type(probability) is not bool
            and math.isfinite(probability) and 0 <= probability <= 1,
            'Invalid probability')
    return min(1 - EPSILON, max(EPSILON, float(probability)))


def binary_log_loss(probability, outcome):
    require(outcome in (0, 1) and type(outcome) is int, 'Invalid binary outcome')
    probability = _clip(probability)
    return -(outcome * math.log(probability) + (1 - outcome) * math.log(1 - probability))


def reliability_bins(pairs, count=10):
    require(type(count) is int and count > 1, 'Invalid reliability bin count')
    bins = [{'count': 0, 'prediction_sum': 0.0, 'outcome_sum': 0} for _ in range(count)]
    for probability, outcome in pairs:
        probability = _clip(probability)
        require(outcome in (0, 1) and type(outcome) is int, 'Invalid reliability outcome')
        index = min(count - 1, int(probability * count))
        bins[index]['count'] += 1
        bins[index]['prediction_sum'] += probability
        bins[index]['outcome_sum'] += outcome
    result = []
    for index, value in enumerate(bins):
        n = value['count']
        result.append({
            'lower': index / count,
            'upper': (index + 1) / count,
            'count': n,
            'mean_prediction': round(value['prediction_sum'] / n, 12) if n else None,
            'observed_rate': round(value['outcome_sum'] / n, 12) if n else None,
        })
    return result


def evaluate_prediction_records(records, *, bin_count=10):
    records = tuple(records)
    require(records, 'No prediction records to evaluate')
    score_losses, one_x_two_losses, one_x_two_briers = [], [], []
    btts_losses, btts_briers, ou_losses, ou_briers = [], [], [], []
    btts_pairs, ou_pairs = [], []
    outcome_names = ('home', 'draw', 'away')
    one_x_two_pairs = {name: [] for name in outcome_names}
    tails = []
    for record in records:
        actual_home, actual_away = record['actual_home'], record['actual_away']
        actual_1x2 = 'home' if actual_home > actual_away else ('draw' if actual_home == actual_away else 'away')
        score_losses.append(-math.log(max(EPSILON, record['score_probability'])))
        probabilities = record['probabilities']['1x2']
        one_x_two_losses.append(-math.log(_clip(probabilities[actual_1x2])))
        one_x_two_briers.append(sum((probabilities[name] - int(name == actual_1x2)) ** 2
                                    for name in outcome_names))
        btts_outcome = int(actual_home > 0 and actual_away > 0)
        btts_probability = record['probabilities']['btts_yes']
        btts_losses.append(binary_log_loss(btts_probability, btts_outcome))
        btts_briers.append((btts_probability - btts_outcome) ** 2)
        btts_pairs.append((btts_probability, btts_outcome))
        ou_outcome = int(actual_home + actual_away >= 3)
        ou_probability = record['probabilities']['ou25_over']
        ou_losses.append(binary_log_loss(ou_probability, ou_outcome))
        ou_briers.append((ou_probability - ou_outcome) ** 2)
        ou_pairs.append((ou_probability, ou_outcome))
        for name in outcome_names:
            one_x_two_pairs[name].append((probabilities[name], int(name == actual_1x2)))
        tails.append(record['tail_mass_bound'])

    mean = lambda values: round(sum(values) / len(values), 12)
    return {
        'prediction_count': len(records),
        'score_log_loss': mean(score_losses),
        '1x2_log_loss': mean(one_x_two_losses),
        '1x2_brier': mean(one_x_two_briers),
        'btts_log_loss': mean(btts_losses),
        'btts_brier': mean(btts_briers),
        'btts_bias': round(mean([value[0] for value in btts_pairs])
                           - mean([value[1] for value in btts_pairs]), 12),
        'ou25_log_loss': mean(ou_losses),
        'ou25_brier': mean(ou_briers),
        'ou25_bias': round(mean([value[0] for value in ou_pairs])
                           - mean([value[1] for value in ou_pairs]), 12),
        'maximum_tail_mass_bound': round(max(tails), 12),
        'reliability': {
            '1x2': {name: reliability_bins(one_x_two_pairs[name], bin_count)
                    for name in outcome_names},
            'btts_yes': reliability_bins(btts_pairs, bin_count),
            'ou25_over': reliability_bins(ou_pairs, bin_count),
        },
    }
