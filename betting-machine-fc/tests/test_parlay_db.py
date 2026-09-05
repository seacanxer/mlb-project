import db


def test_parlay_storage_deduplicates_and_tracks_flat_unit_roi(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "parlays.db"))
    db.init_db()
    payload = {
        "fingerprint": "slate-one",
        "slips": [{
            "tier": "safe", "label": "Tier 1 Safe", "status": "ready",
            "combined_odds": 3.0, "model_joint_probability": 0.3,
            "legs": [
                {"id": "a", "match_id": "1", "match": "A vs B", "home": "A", "away": "B",
                 "league": "L1", "start_ts": 1, "market": "ou", "pick": "Over 2.5", "odds": 1.5},
                {"id": "b", "match_id": "2", "match": "C vs D", "home": "C", "away": "D",
                 "league": "L2", "start_ts": 2, "market": "ah", "pick": "Home -0.5", "odds": 2.0},
            ],
        }],
    }
    assert db.insert_parlay_batch(payload)[0]["created"] is True
    assert db.insert_parlay_batch(payload)[0]["created"] is False
    legs = db.get_pending_parlay_legs()
    db.settle_parlay_leg(legs[0]["id"], "win", 1.5, 3, 0)
    db.settle_parlay_leg(legs[1]["id"], "win", 2.0, 2, 0)
    summary = db.get_parlay_roi()
    assert summary == {"pending": 0, "settled": 1, "wins": 1, "losses": 0,
                       "pushes": 0, "profit_units": 2.0, "roi_pct": 200.0}
