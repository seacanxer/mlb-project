import json
import math
import re
import sqlite3
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone

DB_PATH = "/home/ubuntu/mlb-project/betting-machine-fc/bets.db"
K = 32.0
HOME_ADV = 65.0
BASE_LEAGUE_AVG = 2.6


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = s.encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    s = s.replace(" w ", " ")
    return re.sub(r"\s+", " ", s).strip()


class EloRating:
    def __init__(self):
        self.ratings = {}
        self.league_games = defaultdict(int)
        self.league_teams = defaultdict(set)
        self.league_elo_sum = defaultdict(float)
        self.league_avg = {}
        self.team_games = defaultdict(int)
        self.games = 0

    def _key(self, league, team):
        lg = norm(league)
        t = norm(team)
        return f"{lg}:::{t}"

    def _global_key(self, team):
        return f"GLOBAL:::{norm(team)}"

    def _initial(self, key):
        return self.ratings.get(key, 1500.0)

    def add_result(self, home, away, home_goals, away_goals, league=None, date_ts=None):
        hk = self._key(league, home)
        ak = self._key(league, away)
        hg = self._global_key(home)
        ag = self._global_key(away)
        rh = self._initial(hk) or self._initial(hg)
        ra = self._initial(ak) or self._initial(ag)
        self.ratings.setdefault(hk, rh)
        self.ratings.setdefault(ak, ra)
        self.ratings.setdefault(hg, rh)
        self.ratings.setdefault(ag, ra)
        wh = 1.0 / (1.0 + 10 ** ((ra - rh + HOME_ADV) / 400.0))
        wa = 1.0 - wh
        hgd = (home_goals or 0) - (away_goals or 0)
        if hgd > 0:
            sh, sa = 1.0, 0.0
        elif hgd < 0:
            sh, sa = 0.0, 1.0
        else:
            sh, sa = 0.5, 0.5
        mult = 1.0 + min(abs(hgd) / 2.0, 3.0)
        kh = K * mult
        ka = K * mult
        rh2 = rh + kh * (sh - wh)
        ra2 = ra + ka * (sa - wa)
        self.ratings[hk] = rh2
        self.ratings[ak] = ra2
        self.ratings[hg] = rh2
        self.ratings[ag] = ra2
        lg = norm(league) if league else "unknown"
        self.league_games[lg] += 1
        self.league_teams[lg].add(norm(home))
        self.league_teams[lg].add(norm(away))
        self.league_elo_sum[lg] += rh2 + ra2
        self.team_games[norm(home)] += 1
        self.team_games[norm(away)] += 1
        self.games += 1

    def rating(self, team, league=None):
        key = self._key(league, team) if league else self._global_key(team)
        if key in self.ratings:
            return self.ratings[key]
        gk = self._global_key(team)
        return self.ratings.get(gk, 1500.0)

    def expected(self, home, away, league=None):
        rh = self.rating(home, league)
        ra = self.rating(away, league)
        return 1.0 / (1.0 + 10 ** ((ra - rh + HOME_ADV) / 400.0))

    def drawn_prob(self, home, away, league=None):
        rh = self.rating(home, league)
        ra = self.rating(away, league)
        diff = abs(rh - ra)
        return max(0.22 - diff / 1600.0, 0.12)

    def league_average_elo(self, league):
        lg = norm(league)
        if lg in self.league_avg:
            return self.league_avg[lg]
        n = self.league_games.get(lg, 0)
        if n == 0:
            return 1500.0
        avg = self.league_elo_sum[lg] / (2 * n)
        self.league_avg[lg] = avg
        return avg

    def coverage(self):
        out = {}
        for lg in self.league_games:
            out[lg] = {
                "teams": len(self.league_teams[lg]),
                "games": self.league_games[lg],
                "avg_elo": round(self.league_average_elo(lg), 1),
            }
        return out

    def to_dict(self):
        return {
            "ratings": self.ratings,
            "coverage": self.coverage(),
            "games": self.games,
        }


def expected_goals(engine, home, away, league=None, base_league_avg=BASE_LEAGUE_AVG):
    exp = engine.expected(home, away, league)
    diff = exp - 0.5
    lh = base_league_avg / 2.0 + diff * 2.2
    la = base_league_avg - lh
    lh = max(0.4, min(4.5, lh))
    la = max(0.3, min(4.2, la))
    return lh, la


_ENGINE_CACHE = {"engine": None, "ts": 0.0}
ENGINE_TTL = 900.0


def get_cached_engine(db_path=DB_PATH, ttl=ENGINE_TTL):
    import time
    now = time.time()
    if _ENGINE_CACHE["engine"] is not None and now - _ENGINE_CACHE["ts"] < ttl:
        return _ENGINE_CACHE["engine"]
    engine = build_from_db(db_path)
    _ENGINE_CACHE["engine"] = engine
    _ENGINE_CACHE["ts"] = now
    return engine


def elo_hybrid(home, away, league, market_lh, market_la, weight=0.35, db_path=DB_PATH):
    engine = get_cached_engine(db_path)
    lg = norm(league)
    cov = engine.coverage()
    has_league = (lg in cov and cov[lg]["games"] >= 20)
    team_g = engine.team_games
    both_known = team_g.get(norm(home), 0) >= 2 and team_g.get(norm(away), 0) >= 2
    if not has_league and not both_known:
        return market_lh, market_la, "market+league-prior"
    if not has_league and both_known:
        pass
    lh_e, la_e = expected_goals(engine, home, away, league)
    lh = market_lh * (1.0 - weight) + lh_e * weight
    la = market_la * (1.0 - weight) + la_e * weight
    lh = max(0.30, min(5.0, lh))
    la = max(0.30, min(5.0, la))
    return round(lh, 3), round(la, 3), "market+elo"


def elo_eval_for_board(home, away, league, db_path=DB_PATH):
    engine = get_cached_engine(db_path)
    lg = norm(league)
    cov = engine.coverage()
    team_g = engine.team_games
    has_league = (lg in cov and cov[lg]["games"] >= 20)
    both_known = team_g.get(norm(home), 0) >= 3 and team_g.get(norm(away), 0) >= 3
    if not has_league and not both_known:
        return None
    return evaluate_match(engine, home, away, league)


def evaluate_match(engine, home, away, league=None):
    exp = engine.expected(home, away, league)
    draw = engine.drawn_prob(home, away, league)
    lh, la = expected_goals(engine, home, away, league)
    return {
        "home_elo": round(engine.rating(home, league), 1),
        "away_elo": round(engine.rating(away, league), 1),
        "exp_home": round(exp, 4),
        "exp_away": round(1 - exp, 4),
        "draw_prob": round(draw, 4),
        "home_adv_elo": HOME_ADV,
        "lambda_home": round(lh, 3),
        "lambda_away": round(la, 3),
    }


def build_from_db(db_path=DB_PATH, min_league_games=20):
    engine = EloRating()
    rows = []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT home, away, home_score, away_score, start_ts, league "
            "FROM bets WHERE settled=1 AND home_score IS NOT NULL AND away_score IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()
    for r in sorted(rows, key=lambda x: x["start_ts"] or 0):
        engine.add_result(r["home"], r["away"], r["home_score"], r["away_score"], r["league"], r["start_ts"])
    try:
        import scores_flashscore as sf
        index = sf.fetch_recent_results(days=28, use_cache=True)
        for (hn, an), row in index.items():
            engine.add_result(row["home"], row["away"], row["home_goals"], row["away_goals"],
                              None, None)
    except Exception:
        pass
    drop = [lg for lg, c in engine.coverage().items() if c["games"] < min_league_games]
    for lg in drop:
        engine.league_games.pop(lg, None)
        engine.league_teams.pop(lg, None)
        engine.league_elo_sum.pop(lg, None)
    return engine


if __name__ == "__main__":
    engine = build_from_db()
    cov = engine.coverage()
    top = sorted(cov.items(), key=lambda kv: kv[1]["games"], reverse=True)[:15]
    print(f"total games: {engine.games}")
    print(f"total teams: {len(set(k.split(':::')[1] for k in engine.ratings))}")
    print(f"{'league':40s} {'games':>6s} {'teams':>6s} {'avg_elo':>8s}")
    for lg, c in top:
        print(f"{lg:40s} {c['games']:6d} {c['teams']:6d} {c['avg_elo']:8.1f}")
    print("evaluate sample: Arsenal vs Chelsea")
    print(json.dumps(evaluate_match(engine, "Arsenal", "Chelsea", "England. Premier League"), indent=1))