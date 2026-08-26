/**
 * lib/engine/types.ts
 *
 * Shared typed enums and interfaces for the calculation engine.
 */

// ---------------------------------------------------------------------------
// Final state — typed enum; never free-form strings in engine output
// ---------------------------------------------------------------------------

export type FinalState =
  | 'NEEDS_DATA'
  | 'INVALIDATED'
  | 'SKIP'
  | 'NO_BET'
  | 'T2'
  | 'T1'
  | 'OVER_LEAN'
  | 'OVER_RISKY'
  | 'OVER_STRONG_GAP'
  | 'UNDER_LEAN'
  | 'UNDER_RISKY'
  | 'UNDER_STRONG_GAP';

// ---------------------------------------------------------------------------
// Warning codes — separate from final state
// ---------------------------------------------------------------------------

export type WarningCode =
  | 'OFFENSE_TIER_MISMATCH'
  | 'BORDERLINE_IP'           // IP 30-60; T1 is capped to T2
  | 'RECENT_FORM_WEAK'        // exactly 3 bad starts in the last 5
  | 'MARKET_DISAGREEMENT'     // candidate is priced above the T1 ceiling
  | 'T1_CONFIDENCE_CAPPED'    // score reached T1 but a quality cap applied
  | 'LOW_AVG_SMALL_ERA_GAP'   // AVG < .230 and EraGap < 2.00
  | 'LOW_GAME_LOG_SCORE'      // game-log score <= 4
  | 'LARGE_PRICE_MOVEMENT'
  | 'BULLPEN_WEAKNESS'
  | 'SOURCE_MISMATCH'
  | 'PITCHING_DUEL_RISK'      // both starters WHIP < 1.15 on OVER
  | 'BORDERLINE_SAMPLE'       // IP 60-90 (O/U)
  | 'LINE_MOVEMENT'
  | 'BULLPEN_CONTEXT_RISK'
  | 'EXTREME_PARK_ADJUSTMENT'
  | 'UNDEFINED_MARKET_ANCHOR'
  | 'PARK_FACTOR_FALLBACK'
  | 'OU_RECENT_SAMPLE_INCOMPLETE'
  | 'OU_BULLPEN_SOURCE_LIMITED'
  | 'OU_CONTEXT_NOT_MODELED'
  | 'OU_LINE_MOVE'
  | 'OU_MODEL_MARKET_OUTLIER'
  | 'OU_ERA_WHIP_DIVERGENCE'
  | 'OU_CONFIDENCE_CAPPED'
  | 'OU_PRICE_BELOW_ACTIONABLE'
  | 'OU_PITCHER_LEVEL_FALLBACK'
  | 'ODDS_PROVIDER_NOT_CONFIGURED'
  | 'ODDS_MISSING';           // No odds data at all (provider not configured)

// ---------------------------------------------------------------------------
// Trend for pitcher last-five display
// ---------------------------------------------------------------------------

export type PitcherTrend = 'HOT' | 'COLD' | 'MIXED';

// ---------------------------------------------------------------------------
// Hard gate codes — cause final state to be SKIP / NEEDS_DATA / INVALIDATED
// ---------------------------------------------------------------------------

export type HardGateCode =
  | 'STARTER_TBD'
  | 'STARTER_UNCONFIRMED'
  | 'STARTER_CONFLICTING'
  | 'STARTER_GS_ZERO'
  | 'STARTER_IS_RELIEVER'
  | 'PITCHER_LEVEL_FALLBACK'
  | 'IP_BELOW_MIN'
  | 'INSUFFICIENT_GAME_LOG'
  | 'CANDIDATE_AVG_TOO_LOW'
  | 'TOO_MANY_BAD_STARTS'
  | 'ERA_GAP_NOT_POSITIVE'
  | 'MARKET_FAVORS_DISADVANTAGED'
  | 'ODDS_MISSING_OR_STALE'   // legacy — kept for backward compat
  | 'ODDS_STALE'              // odds provider configured but data is old
  | 'CRITICAL_INPUT_MISSING'
  | 'GAME_ALREADY_STARTED'
  | 'OU_LINE_MISSING'
  | 'OU_STARTER_UNCONFIRMED'
  | 'OU_PITCHER_DATA_MISSING'
  | 'OU_TEAM_RPG_MISSING'
  | 'OU_PARK_FACTOR_MISSING'
  | 'OU_BULLPEN_DATA_MISSING'
  | 'OU_STARTER_IP_BELOW_MIN'
  | 'OU_EXCESSIVE_LINE_MOVE'
  | 'OU_STALE_ODDS'
  | 'OU_PRICE_BELOW_MINIMUM'
  | 'OU_SMALL_GAP';
