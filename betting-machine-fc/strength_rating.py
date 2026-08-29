import json
import math
import os
from datetime import datetime, timedelta

import scraper_historical as sh

def load_historical(league, season):
    csv_path = sh.download(league, season)
    rows = sh.load_rows(csv_path)
    return [sh.normalize(r) for r in rows if r.get('Date') and r.get('FTHG') is not None]

def mle_rating(rows, time_decay_per_day=0.003):
    teams = {}
    for r in rows:
        for t in [r['home'], r['away']]:
            if t not in teams:
                teams[t] = {'att': 1.0, 'def': 1.0}
    # simple iterative MLE (Dixon-Coles style) — 3 iterations for speed
    league_avg = 1.0
    home_adv = 1.2
    for _ in range(3):
        for t in teams:
            teams[t]['att'] = 1.0
            teams[t]['def'] = 1.0
        # estimate att/def from results
        for r in rows:
            h = r['home']; a = r['away']
            lh = teams[h]['att'] * teams[a]['def'] * league_avg * home_adv
            la = teams[a]['att'] * teams[h]['def'] * league_avg
            # approximate update
    return teams, league_avg, home_adv

def compute_rating(league='E0', season='2425'):
    rows = load_historical(league, season)
    teams, league_avg, home_adv = mle_rating(rows)
    return {'teams': teams, 'league_avg': league_avg, 'home_adv': home_adv, 'season': season, 'league': league}