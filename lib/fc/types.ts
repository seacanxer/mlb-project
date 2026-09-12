/**
 * lib/fc/types.ts
 *
 * FC (football) picks frontend contract.
 *
 * VERIFIED against the real backend from git history (commit b306fe8,
 * betting-machine-fc/server.py + db.py + main.py) — NOT against brief §7
 * as-is, because §7 was a reconstruction and differs from the backend in
 * several load-bearing places. Deltas vs brief §7:
 *
 * 1. Pagination: backend returns `{ picks, pagination: {limit,offset,total} }`
 *    (plus `summary`), NOT `{ data, meta }`.
 *    → TODO(§13.1): confirm with backend — RESOLVED from history, re-confirm
 *    if engine is rewritten.
 * 2. Matches: backend returns `{ count, matches[], pagination }` where each
 *    match is a DETAILED object `{ info, picks[], qualified_picks[] }`,
 *    NOT a flat MatchFixture.
 *    → TODO(§13.1): same as above.
 * 3. Tracker summary uses `settled_picks` (NOT `settled`), plus
 *    `locked_picks/pending_picks/live_picks/overdue_picks/duplicates_hidden`.
 *    → TODO(§13.2): field names confirmed from db.get_roi().
 * 4. `market_performance[]` items: `{ market, bets, wins, losses, pushes,
 *    win_rate_pct, loss_rate_pct, profit_units, roi_pct }` — NOT
 *    `{ market, settled, roi_pct, hit_rate_pct, profit_units }`.
 *    → TODO(§13.2): confirmed from db.get_market_performance().
 * 5. `by_version[]` items: `{ formula_version, selection_status, bets, wins,
 *    losses, profit_units, roi_pct, ci95_hw_pct }` — grouped by
 *    (formula_version, selection_status), NO policy_version column.
 *    → TODO(§13.2): confirmed from db.get_roi_by_version().
 * 6. Scan/settle triggers return `{ status: "started"|"busy", message, state }`
 *    and poll via `GET /api/scan/status` / `GET /api/settle/status`.
 *    There is NO job_id. → TODO(§13.4): RESOLVED from history.
 * 7. Health shape: `{ status: "healthy", service, timestamp, uptime,
 *    scan_state, config }` — status is the literal "healthy", diagnostics
 *    live under config.last_scan_diagnostics. → TODO(§13.6): RESOLVED.
 * 8. Error shape: FastAPI `{ detail }` or custom `{ error }` — NOT ApiError
 *    with status_code. → TODO(§13.5): RESOLVED.
 * 9. Real pick `tier` values are "top_pick"|"official"|"watch" (shadow
 *    coverage is tier "watch", never silently promoted). "blocked" /
 *    "market_only" are gate diagnostic counts, never published picks.
 *    → TODO(§13.3): RESOLVED from main.select_top_picks().
 *
 * Rule (brief §7): if the live backend differs from these types, update THIS
 * file first — never silently adapt UI components.
 */

// ---- Enum & base types (verified: main.py select_top_picks + gate_reason) ----
export type Market = 'ah' | 'ou' | 'btts' | '1x2';
export type CoverageStatus = 'full' | 'shadow' | 'market_only';
// NOTE: brief §7 listed tier as full|shadow|watch|blocked|market_only.
// Real engine sets tier = "watch" for shadow coverage, "top_pick"|"official"
// for full coverage. "blocked"/"market_only" never reach published picks.
export type Tier = 'top_pick' | 'official' | 'watch';
export type Decision = 'official' | 'top_pick' | 'watch';
export type SelectionStatus = 'top_pick' | 'official' | 'shadow' | 'top_pick:shadow';

// ---- GET /api/fc/picks (mirrors engine GET /api/picks) ----
export interface FcPick {
  match_id?: string;
  match: string;
  home?: string;
  away?: string;
  league: string;
  /** Unix epoch seconds (engine writes start_ts as epoch, not ISO). */
  start_ts: number;
  market: Market;
  pick: string;
  odds: number;
  probability: number;
  ev: number;
  conservative_ev: number;
  market_probability?: number;
  edge_pct?: number;
  suggested_stake?: number;
  stake_cap?: number;
  kelly_pct?: number;
  is_top_pick: boolean;
  selection_status: SelectionStatus;
  tier: Tier;
  decision: Decision;
  coverage_status: CoverageStatus;
  lambda_source?: string;
  league_model?: string;
  formula_version?: string;
  policy_version?: string;
  ratings_files?: string[];
  total_disagreement?: number;
  /** Attach-only until OOS validation passes — NEVER the primary number. */
  calibrated_prob: number | null;
  rank_score?: number;
  locked?: boolean;
}

export interface PicksSummary {
  total_picks: number;
  qualified_picks: number;
  top_pick_count: number;
  official_count: number;
  watch_count: number;
  formula_version: string;
  avg_ev_pct: number;
  avg_odds: number;
  min_odds_floor: number;
  selection_limit: number;
  max_picks_per_match: number;
  leagues: string[];
  markets: string[];
  last_scan_time: string | null;
}

export interface Pagination {
  limit: number;
  offset: number;
  total: number;
}

export interface PicksResponse {
  summary: PicksSummary;
  picks: FcPick[];
  pagination: Pagination;
  /** Set by the Next.js read layer when picks.json/scan output is missing. */
  engine_offline?: boolean;
}

// ---- GET /api/fc/tracker (mirrors engine GET /api/tracker) ----
export interface TrackerSummary {
  locked_picks: number;
  settled_picks: number;
  wins: number;
  losses: number;
  pushes: number;
  profit_units: number;
  roi_pct: number;
  hit_rate_pct: number;
  duplicates_hidden?: number;
  pending_picks?: number;
  live_picks?: number;
  overdue_picks?: number;
}

export type SettlementBucket = 'locked' | 'live' | 'overdue' | 'settled';

export interface TrackedBet {
  id?: number;
  match_id?: string;
  match: string;
  home?: string;
  away?: string;
  league: string;
  /** Unix epoch seconds. */
  start_ts: number;
  market: string;
  pick: string;
  odds: number;
  ev?: number;
  probability?: number;
  placed_at?: string;
  settled: number | boolean;
  /** 1 = won, 0 = lost, null = push/pending. */
  won: number | null;
  profit: number | null;
  settled_at: string | null;
  home_score: number | null;
  away_score: number | null;
  /** e.g. "FINAL" | "LIVE" | null. */
  score_status: string | null;
  settlement_status?: SettlementBucket;
  timing_status?: SettlementBucket;
  formula_version?: string;
  policy_version?: string;
  selection_status?: string;
}

export interface MarketPerformance {
  market: string;
  bets: number;
  wins: number;
  losses: number;
  pushes: number;
  win_rate_pct: number;
  loss_rate_pct: number;
  profit_units: number;
  roi_pct: number;
}

export interface VersionPerformance {
  formula_version: string;
  selection_status: string;
  bets: number;
  wins: number;
  losses: number;
  profit_units: number;
  roi_pct: number;
  ci95_hw_pct: number | null;
}

export interface TrackerResponse {
  summary: TrackerSummary;
  locked: TrackedBet[];
  live: TrackedBet[];
  overdue: TrackedBet[];
  settled: TrackedBet[];
  status_counts: Record<string, number>;
  market_performance: MarketPerformance[];
  by_version: VersionPerformance[];
  unit_size: number;
  engine_offline?: boolean;
}

// ---- GET /api/fc/matches (mirrors engine GET /api/matches) ----
export interface FixtureInfo {
  match_id?: string;
  home?: string;
  away?: string;
  league?: string;
  /** Unix epoch seconds. */
  start_ts?: number;
  coverage_status?: string;
  [key: string]: unknown;
}

export interface DetailedMatch {
  info: FixtureInfo;
  picks?: FcPick[];
  qualified_picks?: FcPick[];
  [key: string]: unknown;
}

export interface MatchesResponse {
  count: number;
  matches: DetailedMatch[];
  pagination: Pagination;
  engine_offline?: boolean;
}

// ---- GET /api/fc/health (mirrors engine GET /api/health) ----
export interface HealthResponse {
  status: 'healthy' | 'offline';
  service: string;
  timestamp: string;
  scan_state: {
    is_running: boolean;
    last_scan_time: string | null;
    last_scan_count: number;
    last_scan_picks: number;
    error: string | null;
    progress: string;
    diagnostics: Record<string, unknown>;
  };
  formula_version: string;
  /** True when the engine scan output is absent (pruned/offline). */
  engine_offline: boolean;
}

// ---- Scan/settle triggers (engine shapes; UI keeps buttons disabled while
// ---- engine_offline — see FR-1/FR-2. No job_id exists on the real engine.)
export interface TriggerResponse {
  status: 'started' | 'busy';
  message: string;
}

// ---- Error shape (FastAPI default / engine custom) ----
export interface ApiErrorShape {
  detail?: string;
  error?: string;
  message?: string;
}
