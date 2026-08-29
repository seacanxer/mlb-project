import db
import scores_flashscore as sf
from model import ah_payout, ah_payout_away
from datetime import date, timedelta


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


def _kickoff_date_ok(bet, row):
    """Allow the locked fixture's kickoff date to match the result date,
    with one day of slack for timezone differences."""
    ts = bet.get("start_ts") or 0
    if not ts:
        return False
    kick = date.fromtimestamp(ts)
    rdate = row.get("date_key") or ""
    if not rdate:
        return False
    allowed = {(kick + timedelta(days=i)).isoformat() for i in (0, 1)}
    return rdate in allowed


def settle_all():
    """Settle each lock from flashscore.mobi final scores."""
    settled_count = 0
    matched = 0
    index = sf.fetch_recent_results(days=9)
    lookup = sf.build_lookup(index)
    for bet in db.get_unsettled():
        row = sf.find_result(bet.get("home"), bet.get("away"), lookup)
        if not row:
            continue
        if not _kickoff_date_ok(bet, row):
            continue
        matched += 1
        home_goals = row["home_goals"]
        away_goals = row["away_goals"]
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
        'matched_results': matched,
    }
