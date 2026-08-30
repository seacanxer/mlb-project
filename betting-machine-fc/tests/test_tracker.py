import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
import scores_flashscore as sf
from settlement import _allowed_result_dates


def _insert_raw(conn, *, match, start_ts, market, pick, settled, won, profit):
    conn.execute(
        '''
        INSERT INTO bets (
            match, home, away, league, start_ts, market, pick, odds, ev,
            probability, placed_at, settled, won, profit, settled_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            match, "Home", "Away", "Test League", start_ts, market, pick,
            1.90, 0.08, 0.57, "2026-08-30T00:00:00", settled, won,
            profit, "2026-08-30T03:00:00" if settled else None,
        ),
    )


def test_tracker_deduplicates_without_deleting_history(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "bets.db"))
    db.init_db()
    conn = db._connect()
    for offset in range(3):
        _insert_raw(
            conn, match="Manchester United vs Ipswich Town", start_ts=100 + offset,
            market="btts", pick="BTTS Yes", settled=1, won=1, profit=0.78,
        )
    _insert_raw(
        conn, match="Manchester United vs Ipswich Town", start_ts=500,
        market="btts", pick="BTTS Yes", settled=0, won=0, profit=0.0,
    )
    conn.commit()
    raw_count = conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0]
    conn.close()

    assert raw_count == 4
    assert len(db.get_settled()) == 1
    assert db.get_unsettled() == []
    summary = db.get_roi()
    assert summary["settled_picks"] == 1
    assert summary["wins"] == 1
    assert summary["profit_units"] == 0.78
    assert summary["duplicates_hidden"] == 3

    markets = db.get_market_performance()
    assert markets == [{
        "market": "btts", "bets": 1, "wins": 1, "losses": 0,
        "pushes": 0, "win_rate_pct": 100.0, "loss_rate_pct": 0.0,
        "profit_units": 0.78, "roi_pct": 78.0,
    }]


def test_result_matching_prefers_fixture_date():
    index = {
        ("home", "away"): {
            "home": "Home", "away": "Away", "home_goals": 1,
            "away_goals": 0, "date_key": "2026-08-20",
        },
        ("home fc", "away fc"): {
            "home": "Home FC", "away": "Away FC", "home_goals": 2,
            "away_goals": 1, "date_key": "2026-08-30",
        },
    }
    lookup = sf.build_lookup(index)
    row = sf.find_result("Home", "Away", lookup, allowed_dates={"2026-08-30"})
    assert row is not None
    assert row["date_key"] == "2026-08-30"
    assert (row["home_goals"], row["away_goals"]) == (2, 1)


def test_allowed_settlement_dates_include_timezone_slack():
    kickoff = int(datetime(2026, 8, 30, 23, 30, tzinfo=timezone.utc).timestamp())
    assert _allowed_result_dates({"start_ts": kickoff}) == {
        "2026-08-29", "2026-08-30", "2026-08-31",
    }
