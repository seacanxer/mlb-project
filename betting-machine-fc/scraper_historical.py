import csv
import os
import urllib.request

BASE = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"
UA = {"User-Agent": "Mozilla/5.0"}

LEAGUES = {
    "england": "E0",
    "spain": "SP1",
    "germany": "D1",
    "italy": "I1",
    "france": "F1",
    "netherlands": "N1",
    "portugal": "P1",
    "belgium": "B1",
    "turkey": "T1",
    "greece": "G1",
    "scotland": "SC0",
}


def season_code(year):
    return f"{str(year)[2:]}{str(year + 1)[2:]}"


def download(league_code, season, out_dir="data", force=False):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{league_code}_{season}.csv")
    if not force and os.path.exists(path) and os.path.getsize(path) > 100:
        return path
    url = BASE.format(season=season, league=league_code)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    with open(path, "wb") as f:
        f.write(data)
    return path


def load_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def normalize(row):
    def num(key):
        try:
            return float(row[key])
        except (KeyError, ValueError):
            return None

    return {
        "date": row.get("Date"),
        "home": row.get("HomeTeam"),
        "away": row.get("AwayTeam"),
        "fthg": num("FTHG"),
        "ftag": num("FTAG"),
        "odds_home": num("B365H"),
        "odds_draw": num("B365D"),
        "odds_away": num("B365A"),
        "odds_over": num("B365>2.5"),
        "odds_under": num("B365<2.5"),
        "ah_line": num("AHh"),
        "ah_home": num("B365AHH"),
        "ah_away": num("B365AHA"),
    }


if __name__ == "__main__":
    import sys

    season = sys.argv[1] if len(sys.argv) > 1 else season_code(2025)
    for name, code in LEAGUES.items():
        try:
            p = download(code, season)
            print(f"OK {name} {code}: {len(load_rows(p))} rows -> {p}")
        except Exception as e:
            print(f"ERR {name} {code}: {e}")