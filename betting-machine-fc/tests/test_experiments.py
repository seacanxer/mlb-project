import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db


def _bet(**kw):
    base = {"match": "A vs B", "home": "A", "away": "B", "league": "L",
            "start_ts": 100, "market": "ou", "pick": "Over 2.5", "odds": 1.9,
            "ev": 0.1, "probability": 0.6, "formula_version": "v-test",
            "policy_version": "quality-v1", "selection_status": "official"}
    base.update(kw)
    return base


def test_roi_by_version_splits_cohorts(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "bets.db"))
    db.init_db()
    for i, (fv, won, profit) in enumerate([
            ("v1", 1, 0.9), ("v1", 0, -1.0),
            ("v2", 1, 0.9), ("v2", 1, 0.85)]):
        bid, _ = db.insert_bet(_bet(match=f"M{i} vs N{i}", start_ts=100 + i))
        c = db._connect()
        c.execute("UPDATE bet_audit SET formula_version=? WHERE bet_id=?", (fv, bid))
        c.commit()
        c.close()
        db.settle_bet(bid, bool(won), profit)
    rows = db.get_roi_by_version()
    by_fv = {r["formula_version"]: r for r in rows}
    assert by_fv["v1"]["bets"] == 2
    assert by_fv["v1"]["roi_pct"] == round((0.9 - 1.0) / 2 * 100, 2)
    assert by_fv["v2"]["bets"] == 2
    assert by_fv["v2"]["roi_pct"] == round((0.9 + 0.85) / 2 * 100, 2)
    assert by_fv["v2"]["ci95_hw_pct"] is not None
    assert by_fv["v2"]["ci95_hw_pct"] >= 0


def test_run_experiment_logs_all_runs(tmp_path, monkeypatch):
    import run_experiment
    import scraper_historical as sh
    csv = tmp_path / "E0_2526.csv"
    lines = ["Date,HomeTeam,AwayTeam,FTHG,FTAG,B365H,B365D,B365A,B365>2.5,B365<2.5"]
    for i in range(8):
        lines.append(f"{i + 1:02d}/08/2025,TeamA,TeamB,{2 + (i % 2)},{i % 2},2.2,3.4,3.2,1.9,1.95")
    csv.write_text("\n".join(lines))
    monkeypatch.setattr(sh, "download", lambda *a, **k: str(csv))
    log = str(tmp_path / "exp.jsonl")
    monkeypatch.setattr(run_experiment, "LOG_PATH", log)
    import argparse
    args = argparse.Namespace(name="t", leagues=["E0"], season="2526",
                              min_odds=1.5, min_ev=0.0, log=log)
    orig_parse = argparse.ArgumentParser.parse_args
    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", lambda self: args)
    try:
        run_experiment.main()
    finally:
        monkeypatch.setattr(argparse.ArgumentParser, "parse_args", orig_parse)
    rows = [json.loads(line) for line in open(log, encoding="utf-8")]
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "t" and row["league"] == "E0"
    assert "baseline" in row and "model" in row
    assert row["baseline"]["n"] > 0
