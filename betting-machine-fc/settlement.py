import db
import scraper_1xbit as sc
from model_v2 import ah_payout, ah_payout_away


def total_payout(line, side, odds, goals):
    lines = [line, line] if abs((line * 2) - round(line * 2)) < 1e-9 else [line - 0.25, line + 0.25]
    returned = 0.0
    for leg in lines:
        adjusted = goals - leg
        side_adjusted = adjusted if side == 'over' else -adjusted
        if side_adjusted > 1e-9:
            returned += odds
        elif abs(side_adjusted) <= 1e-9:
            returned += 1.0
    return returned / len(lines)


def settle_all():
    """Settle each lock from its provider event id, including removed fixtures."""
    settled_count = 0
    legacy_without_match_id = 0
    for bet in db.get_unsettled():
        match_id = bet.get('source_match_id')
        if not match_id:
            legacy_without_match_id += 1
            continue

        result = sc.get_match(match_id)
        if result.get('WP') != 3:
            continue

        home_goals = int(result.get('G1', 0))
        away_goals = int(result.get('G2', 0))
        total = home_goals + away_goals
        margin = home_goals - away_goals
        won = False
        profit = -1.0

        if bet['market'] == '1x2':
            if 'Home' in bet['pick']:
                won = margin > 0
            elif 'Draw' in bet['pick']:
                won = margin == 0
            elif 'Away' in bet['pick']:
                won = margin < 0
        elif bet['market'] == 'ou':
            line = float(bet['pick'].split()[1])
            side = 'over' if 'Over' in bet['pick'] else 'under'
            profit = total_payout(line, side, bet['odds'], total) - 1.0
            won = True if profit > 0 else (False if profit < 0 else None)
        elif bet['market'] == 'btts':
            both_scored = home_goals >= 1 and away_goals >= 1
            won = both_scored if 'Yes' in bet['pick'] else not both_scored
        elif bet['market'] == 'ah':
            line = float(bet['pick'].split()[1])
            payout = (ah_payout(line, bet['odds'], margin)
                      if 'Home' in bet['pick']
                      else ah_payout_away(line, bet['odds'], margin))
            profit = payout - 1.0
            won = True if profit > 0 else (False if profit < 0 else None)

        if bet['market'] not in ('ah', 'ou'):
            profit = (bet['odds'] - 1.0) if won else -1.0
        db.settle_bet(bet['id'], won, profit)
        settled_count += 1

    return {
        'settled_now': settled_count,
        'legacy_without_match_id': legacy_without_match_id,
    }
