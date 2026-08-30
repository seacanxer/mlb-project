import db
import scores_flashscore as sf
from model import ah_payout, ah_payout_away
from datetime import date, timedelta
import time


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
    ts = bet.get("start_ts") or 0
    if not ts:
        return False
    kick = date.fromtimestamp(ts)
    rdate = row.get("date_key") or ""
    if not rdate:
        return False
    allowed = {(kick + timedelta(days=i)).isoformat() for i in (0, 1)}
    return rdate in allowed


def _kickoff_time_ok(bet):
    ts = bet.get("start_ts") or 0
    if not ts:
        return False
    return time.time() >= ts - 1800


def settle_all():
    """Settle locks and backfill missing final scores from FlashScore."""
    settled_count = 0
    scores_backfilled = 0
    matched = 0
    unsettled = db.get_unsettled()
    missing_scores = [
        bet for bet in db.get_settled()
        if bet.get('home_score') is None or bet.get('away_score') is None
    ]
    candidates = unsettled + missing_scores

    # 1. Try API-Football for recent days
    import scores_api_football as sf_api
    index_api = sf_api.fetch_recent_results(days=3, use_cache=False)
    lookup_api = sf_api.build_lookup(index_api)
    for bet in candidates:
        kickoff_date = date.fromtimestamp(bet.get("start_ts")) if bet.get("start_ts") else None
        row = sf_api.find_result(bet.get("home"), bet.get("away"), lookup_api, kickoff_date=kickoff_date)
        if not row:
            continue
        if not _kickoff_date_ok(bet, row):
            continue
        if not _kickoff_time_ok(bet):
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
        db.settle_bet(
            bet['id'], won, profit,
            home_score=home_goals,
            away_score=away_goals,
            score_status='final',
        )
        if bet.get('settled'):
            scores_backfilled += 1
        else:
            settled_count += 1

    # 2. If no settlement from API, fallback to FlashScore
    if settled_count == 0:
        index_fs = sf.fetch_recent_results(days=9)
        lookup_fs = sf.build_lookup(index_fs)
        for bet in candidates:
            kickoff_date = date.fromtimestamp(bet.get("start_ts")) if bet.get("start_ts") else None
            row = sf.find_result(bet.get("home"), bet.get("away"), lookup_fs, kickoff_date=kickoff_date)
            if not row:
                continue
            if not _kickoff_date_ok(bet, row):
                continue
            if not _kickoff_time_ok(bet):
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
            db.settle_bet(
                bet['id'], won, profit,
                home_score=home_goals,
                away_score=away_goals,
                score_status='final',
            )
            if bet.get('settled'):
                scores_backfilled += 1
            else:
                settled_count += 1

    result_count = len(index_api) if 'index_api' in locals() else len(index_fs) if 'index_fs' in locals() else 0
    return {
        'settled_now': settled_count,
        'scores_backfilled': scores_backfilled,
        'matched_results': matched,
        'result_count': result_count,
        'unsettled': len(unsettled),
    }
