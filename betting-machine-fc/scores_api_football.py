"""DEPRECATED — API-Football feed module (account suspended).

This module is no longer used by settlement.py. FlashScore.mobi is now the
primary feed, with scores_alt.py (TheSportsDB + OpenLigaDB) as fallback.

Kept as an empty stub. The original implementation was removed because:
  1. The API key is suspended (account blocked).
  2. find_result() contained a dangerous fuzzy fallback (threshold 0.3)
     that could fabricate scores from unrelated matches — the same class
     of bug that was already removed from scores_flashscore.py.

If you need historical reference, check git history for the original file.
"""
