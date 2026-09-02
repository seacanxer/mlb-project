import db
import scores_flashscore as sf
from model import ah_payout, ah_payout_away
from datetime import date, datetime, timedelta, timezone
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
    # FlashScore and API-Football feed dates are UTC-based; server timezone
    # may be CST (UTC+8), so a naive date.fromtimestamp() shifts the day.
    # Convert via UTC explicitly and tolerate a ±2 day window (some feeds
    # publish the local fixture date, and Americas matches that start late
    # at night UTC can appear on the next calendar day in the feed).
    kick = datetime.fromtimestamp(ts, timezone.utc).date()
    rdate = row.get("date_key") or ""
    if not rdate:
        return False
    allowed = {(kick + timedelta(days=i)).isoformat() for i in (-2, -1, 0, 1, 2)}
    return rdate in allowed


def _kickoff_time_ok(bet):
    ts = bet.get("start_ts") or 0
    if not ts:
        return False
    # Final results only: never settle before the match has had time to end.
    # 105 min buffer (90' + HT + stoppage); worker re-checks every 15 min.
    return time.time() >= ts + 6300


def recheck_premature():
    """Reset settled bets whose settlement timestamp predates kickoff + 105 min.

    Those were settled before the match could possibly have ended (old guard /
    stale server process) — their result was never actually known. Resetting
    them puts them back in the normal settle_all queue so the refresh button
    can re-settle them with the correct guard and a real final score.
    """
    reset_count = 0
    for b in db.get_settled():
        sa = b.get("settled_at")
        ts = b.get("start_ts") or 0
        if not sa or not ts:
            continue
        try:
            settled_ts = datetime.fromisoformat(sa.replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
        if settled_ts < ts + 6300:
            db.reset_bet(b["id"])
            reset_count += 1
    return reset_count


def _settle_candidates_with(candidates, lookup, find_result, skip_ids=None):
    """Run one results feed over the candidate bets; shared by both feeds."""
    if skip_ids is None:
        skip_ids = set()
    settled_count = 0
    scores_backfilled = 0
    matched = 0
    for bet in candidates:
        if bet["id"] in skip_ids:
            continue
        ts = bet.get("start_ts")
        kickoff_date = (datetime.fromtimestamp(float(ts), timezone.utc).date() if ts else None)
        row = find_result(bet.get("home"), bet.get("away"), lookup, kickoff_date=kickoff_date)
        if not row:
            continue
        if not _kickoff_date_ok(bet, row):
            continue
        if not _kickoff_time_ok(bet):
            continue

        # --- YOUTH MATCH PROTECTION (settlement-level) ---
        # For age-category bets (U17–U23), double-check that the matched
        # result is from a youth league. This is a belt-and-suspenders check
        # that runs even if the feed's find_result already validated.
        import scores_flashscore as _sf_mod
        age = _sf_mod.is_youth_bet(bet.get("home"), bet.get("away"))
        if age:
            league = (row.get("league") or "").lower()
            # Accept if league contains the age suffix or is a known youth league
            if age.lower() not in league and not _sf_mod._YOUTH_LEAGUE_RE.search(league):
                # Also accept if both team names have the age suffix
                h_age = bool(_sf_mod._YOUTH_RE.search(row.get("home") or ""))
                a_age = bool(_sf_mod._YOUTH_RE.search(row.get("away") or ""))
                if not (h_age and a_age):
                    continue  # skip — likely a senior match with similar name
        matched += 1
        home_goals = row["home_goals"]
        away_goals = row["away_goals"]
        total = home_goals + away_goals
        margin = home_goals - away_goals
        won = False
        profit = -1.0

        if bet["market"] == "1x2":
            if "Home" in bet["pick"]:
                won = margin > 0
            elif "Draw" in bet["pick"]:
                won = margin == 0
            elif "Away" in bet["pick"]:
                won = margin < 0
        elif bet["market"] == "ou":
            line = float(bet["pick"].split()[1])
            side = "over" if "Over" in bet["pick"] else "under"
            profit = total_payout(line, side, bet["odds"], total) - 1.0
            won = True if profit > 0 else (False if profit < 0 else None)
        elif bet["market"] == "btts":
            both_scored = home_goals >= 1 and away_goals >= 1
            won = both_scored if "Yes" in bet["pick"] else not both_scored
        elif bet["market"] == "ah":
            line = float(bet["pick"].split()[1])
            payout = (ah_payout(line, bet["odds"], margin)
                      if "Home" in bet["pick"]
                      else ah_payout_away(line, bet["odds"], margin))
            profit = payout - 1.0
            won = True if profit > 0 else (False if profit < 0 else None)

        if bet["market"] not in ("ah", "ou"):
            profit = (bet["odds"] - 1.0) if won else -1.0
        db.settle_bet(
            bet["id"], won, profit,
            home_score=home_goals,
            away_score=away_goals,
            score_status="final",
        )
        skip_ids.add(bet["id"])
        if bet.get("settled"):
            scores_backfilled += 1
        else:
            settled_count += 1
    return settled_count, scores_backfilled, matched


def settle_all():
    """Settle locks and backfill missing final scores from FlashScore (primary)
    with scores_alt (TheSportsDB + OpenLigaDB) as fallback.

    Feed order:
      1. FlashScore.mobi — primary, 7-day window, ~4000+ matches/day.
         Carries the vast majority of leagues worldwide.
      2. scores_alt — fallback for bets FlashScore could not match.
         Covers major European leagues + MLS/Brazil via TheSportsDB
         and German leagues via OpenLigaDB. No API key required.

    API-Football (formerly primary) was removed: its API key is suspended,
    and its find_result() still contained a dangerous fuzzy fallback
    (threshold 0.3) that could fabricate scores from unrelated matches.
    """
    unsettled = db.get_unsettled()
    missing_scores = [
        bet for bet in db.get_settled()
        if bet.get("home_score") is None or bet.get("away_score") is None
    ]
    candidates = unsettled + missing_scores
    skip_ids = set()

    # 1. FlashScore (primary feed).
    index_fs = sf.fetch_recent_results(days=7)
    lookup_fs = sf.build_lookup(index_fs)
    settled_count, scores_backfilled, matched = _settle_candidates_with(
        candidates, lookup_fs, sf.find_result, skip_ids
    )

    # 2. Alternative feeds (fallback) — only for bets FlashScore missed.
    import scores_alt as sf_alt
    index_alt = sf_alt.fetch_recent_results(days=3)
    lookup_alt = sf_alt.build_lookup(index_alt)
    s2, b2, m2 = _settle_candidates_with(
        candidates, lookup_alt, sf_alt.find_result, skip_ids
    )
    settled_count += s2
    scores_backfilled += b2
    matched += m2

    # Report the primary feed's count; fallback is supplementary.
    result_count = len(index_fs)
    return {
        "settled_now": settled_count,
        "scores_backfilled": scores_backfilled,
        "matched_results": matched,
        "result_count": result_count,
        "unsettled": len(unsettled),
    }