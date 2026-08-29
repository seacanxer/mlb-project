import json
import os
from datetime import datetime

import db
import scraper_1xbit as sc
from model_v2 import match_probs, btts_prob, over_prob, under_prob, ah_ev, ah_ev_away, ev

def settle_all():
    matches = sc.list_matches()
    for m in matches:
        v = sc.get_match(m['I'])
        o = sc.extract_markets(v)
        # check if match finished (WP=3)
        if v.get('WP') != 3:
            continue
        home_goals = v.get('G1', 0)
        away_goals = v.get('G2', 0)
        total = home_goals + away_goals
        margin = home_goals - away_goals
        # find all unsettled bets for this match
        bets = db.get_bets(settled=False)
        for bet in bets:
            if bet['match'] != f"{o['home']} vs {o['away']}":
                continue
            won = False
            if bet['market'] == '1x2':
                if 'Home' in bet['pick']:
                    won = margin > 0
                elif 'Draw' in bet['pick']:
                    won = margin == 0
                elif 'Away' in bet['pick']:
                    won = margin < 0
            elif bet['market'] == 'ou':
                if 'Over' in bet['pick']:
                    won = total > 2.5
                else:
                    won = total < 2.5
            elif bet['market'] == 'btts':
                won = home_goals >= 1 and away_goals >= 1
            elif bet['market'] == 'ah':
                # simplified: use model's ah_ev to determine cover? better: use actual margin
                # we just approximate based on pick string
                pick = bet['pick']
                if 'Home' in pick:
                    try:
                        line = float(pick.split()[1])
                    except:
                        line = 0.0
                    won = margin + line > 0
                else:
                    try:
                        line = float(pick.split()[1])
                    except:
                        line = 0.0
                    won = -margin + line > 0
            profit = (bet['odds'] - 1.0) if won else -1.0
            db.settle_bet(bet['id'], won, profit)
    return {'settled': len([b for b in db.get_bets(settled=True) if b['settled_at'] > datetime.now().isoformat()])}