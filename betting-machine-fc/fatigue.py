# ============================================================================
# fatigue.py — rest-days & congestion adjustment for Dixon-Coles lambdas.
#
# Documented assumptions (tunable constants below):
#  - Short rest hurts scoring AND defending. Tired team's attack λ × f,
#    opponent's attack λ × min(2 - f, 1.05) (tired defence concedes more,
#    capped so one factor never dominates).
#  - f by rest days since previous match: >=5d → 1.00 (full rest),
#    3-5d → 0.99, 2-3d → 0.97, <2d → 0.94 (back-to-back).
#  - Congestion (>=3 matches in prior 7d incl. current window): extra ×0.98
#    on the congested side's attack.
#  - Ledger: data/team_ledger.json {norm_name: [unix_ts ... last 10]}.
#    Live scans persist it; backtests use an ephemeral dict (no leakage
#    across runs, chronological order required from caller).
# stdlib only.
# ============================================================================
import json
import os
import re
import time
import unicodedata

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LEDGER_PATH = os.path.join(BASE_DIR, "data", "team_ledger.json")
MAX_KEPT = 10

FULL_REST_D = 5.0
TIER2_D = 3.0
TIER3_D = 2.0
CONGEST_WINDOW_S = 7 * 86400
CONGEST_MIN_COUNT = 3
OPP_BOOST_CAP = 1.05


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = s.encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def rest_factor(rest_days):
    if rest_days is None or rest_days >= FULL_REST_D:
        return 1.0
    if rest_days >= TIER2_D:
        return 0.99
    if rest_days >= TIER3_D:
        return 0.97
    return 0.94


def load_ledger(path=LEDGER_PATH):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {k: sorted(v)[-MAX_KEPT:] for k, v in data.items() if isinstance(v, list)}
    except Exception:
        return {}


def save_ledger(ledger, path=LEDGER_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({k: sorted(v)[-MAX_KEPT:] for k, v in ledger.items()}, f)
    os.replace(tmp, path)


def record_fixtures(ledger, fixtures):
    """fixtures: iterable of (home, away, start_ts). Returns ledger."""
    for home, away, ts in fixtures:
        if not ts:
            continue
        for team in (home, away):
            k = norm(team)
            if not k:
                continue
            lst = ledger.setdefault(k, [])
            if ts not in lst:
                lst.append(ts)
                if len(lst) > MAX_KEPT:
                    del lst[:-MAX_KEPT]
    return ledger


def _rest_info(team, start_ts, ledger):
    """(rest_days|None, congested:bool) for one team before start_ts."""
    if not start_ts:
        return None, False
    hist = sorted(t for t in ledger.get(norm(team), []) if t < start_ts)
    if not hist:
        return None, False
    rest_days = (start_ts - hist[-1]) / 86400.0
    recent = [t for t in hist if start_ts - t <= CONGEST_WINDOW_S]
    congested = len(recent) >= CONGEST_MIN_COUNT - 1 and rest_days < FULL_REST_D
    return rest_days, congested


def apply_rest_adjustment(home, away, start_ts, lh, la, ledger=None):
    """Scale (lh, la) for short rest / congestion.
    Returns (lh2, la2, info). No history → unchanged (factor 1.0)."""
    ledger = ledger or {}
    hr, hcong = _rest_info(home, start_ts, ledger)
    ar, acong = _rest_info(away, start_ts, ledger)
    hf = rest_factor(hr) * (0.98 if hcong else 1.0)
    af = rest_factor(ar) * (0.98 if acong else 1.0)
    lh2 = round(lh * hf * min(2.0 - af, OPP_BOOST_CAP), 3)
    la2 = round(la * af * min(2.0 - hf, OPP_BOOST_CAP), 3)
    info = {"home_rest_d": hr, "away_rest_d": ar,
            "home_congested": hcong, "away_congested": acong,
            "home_factor": round(hf, 4), "away_factor": round(af, 4)}
    return lh2, la2, info