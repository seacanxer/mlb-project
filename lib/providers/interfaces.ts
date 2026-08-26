/**
 * lib/providers/interfaces.ts
 *
 * Provider interface contracts for all external data sources.
 * Concrete implementations swap in without changing calculation code.
 */

import { z } from 'zod';

// ---------------------------------------------------------------------------
// Shared schemas
// ---------------------------------------------------------------------------

export const FreshnessState = z.enum(['fresh', 'stale', 'missing', 'conflicting']);
export type FreshnessState = z.infer<typeof FreshnessState>;

export const ProviderResult = <T extends z.ZodTypeAny>(dataSchema: T) =>
  z.object({
    provider: z.string(),
    providerId: z.string().optional(),
    sourceIdentifier: z.string().optional(),
    retrievedAt: z.date(),
    effectiveAt: z.date().optional(),
    season: z.number().int().optional(),
    sourceTimezone: z.string().optional(),
    rawChecksum: z.string(),
    data: dataSchema,
    freshnessState: FreshnessState,
    validationWarnings: z.array(z.string()).default([]),
  });

// ---------------------------------------------------------------------------
// Schedule
// ---------------------------------------------------------------------------

export const ScheduledGame = z.object({
  gameId: z.string(),
  date: z.string(), // YYYY-MM-DD (ET)
  startTimeUtc: z.date(),
  homeTeamId: z.string(),
  awayTeamId: z.string(),
  venueId: z.string(),
  season: z.number().int(),
  status: z.enum(['scheduled', 'in_progress', 'final', 'postponed', 'cancelled']),
  homeTeamName: z.string(),
  awayTeamName: z.string(),
  venueName: z.string(),
  homeStarterPersonId: z.string().optional(),
  awayStarterPersonId: z.string().optional(),
  homeStarterName: z.string().optional(),
  awayStarterName: z.string().optional(),
  homeTeamAbbreviation: z.string().optional(),
  awayTeamAbbreviation: z.string().optional(),
  homeTeamCity: z.string().optional(),
  awayTeamCity: z.string().optional(),
  homeLeagueId: z.number().int().optional(),
  awayLeagueId: z.number().int().optional(),
  homeDivisionId: z.number().int().optional(),
  awayDivisionId: z.number().int().optional(),
});
export type ScheduledGame = z.infer<typeof ScheduledGame>;

export interface ScheduleProvider {
  getSchedule(date: string): Promise<z.infer<ReturnType<typeof ProviderResult<typeof ScheduledGame>>>[]>;
}

// ---------------------------------------------------------------------------
// Pitcher stats
// ---------------------------------------------------------------------------

export const PitcherSeasonStats = z.object({
  personId: z.string(),
  season: z.number().int(),
  era: z.number(),
  whip: z.number(),
  inningsPitched: z.number(), // raw value e.g. 5.2
  outsRecorded: z.number().int(),
  gamesStarted: z.number().int(),
  earnedRuns: z.number().int(),
  walks: z.number().int(),
  strikeouts: z.number().int(),
});
export type PitcherSeasonStats = z.infer<typeof PitcherSeasonStats>;

export const PitcherGameLog = z.object({
  personId: z.string(),
  gameDate: z.string(),
  season: z.number().int(),
  earnedRuns: z.number().int(),
  outsRecorded: z.number().int(),
  gameEra: z.number(),
  isGoodStart: z.boolean(),
});
export type PitcherGameLog = z.infer<typeof PitcherGameLog>;

export interface PitcherStatsProvider {
  getSeasonStats(personId: string, season: number): Promise<z.infer<ReturnType<typeof ProviderResult<typeof PitcherSeasonStats>>>>;
  getGameLogs(personId: string, season: number, lastN?: number): Promise<z.infer<ReturnType<typeof ProviderResult<typeof PitcherGameLog>>>[]>;
}

// ---------------------------------------------------------------------------
// Team stats
// ---------------------------------------------------------------------------

export const TeamSeasonStats = z.object({
  teamId: z.string(),
  season: z.number().int(),
  avg: z.number(),
  ops: z.number(),
  runsPerGame: z.number(),
  bullpenEra: z.number().optional(),
  bullpenWhip: z.number().optional(),
  wins: z.number().int(),
  losses: z.number().int(),
  last10Wins: z.number().int(),
  last10Losses: z.number().int(),
  currentStreak: z.number().int(), // positive = win streak, negative = loss streak
});
export type TeamSeasonStats = z.infer<typeof TeamSeasonStats>;

export interface TeamStatsProvider {
  getTeamStats(teamId: string, season: number): Promise<z.infer<ReturnType<typeof ProviderResult<typeof TeamSeasonStats>>>>;
}

export const BullpenStats = z.object({
  teamId: z.string(),
  season: z.number().int(),
  era: z.number(),
  whip: z.number(),
  inningsPitched: z.string(),
  outsRecorded: z.number().int(),
  relievers: z.number().int(),
  gamesPitched: z.number().int(),
  earnedRuns: z.number().int(),
  walks: z.number().int(),
  hits: z.number().int(),
  strikeouts: z.number().int(),
  excludedSwingmen: z.number().int(),
  skippedWithoutStats: z.number().int(),
});
export type BullpenStats = z.infer<typeof BullpenStats>;

export interface BullpenStatsProvider {
  getTeamBullpen(teamId: string, season: number): Promise<z.infer<ReturnType<typeof ProviderResult<typeof BullpenStats>>>>;
}

// ---------------------------------------------------------------------------
// Odds
// ---------------------------------------------------------------------------

export const OddsData = z.object({
  gameId: z.string(),
  moneylineHome: z.number().optional(), // decimal
  moneylineAway: z.number().optional(), // decimal
  moneylineHomeOrig: z.string().optional(),
  moneylineAwayOrig: z.string().optional(),
  totalLine: z.number().optional(),
  totalOverDecimal: z.number().optional(),
  totalUnderDecimal: z.number().optional(),
});
export type OddsData = z.infer<typeof OddsData>;

export interface OddsProvider {
  getOdds(gameId: string): Promise<z.infer<ReturnType<typeof ProviderResult<typeof OddsData>>> | null>;
  importManual(payload: unknown): Promise<OddsData[]>;
  isConfigured(): boolean;
}

// ---------------------------------------------------------------------------
// Park factors
// ---------------------------------------------------------------------------

export const ParkFactorData = z.object({
  venueId: z.string(),
  season: z.number().int(),
  factor: z.number(),
  source: z.string(),
  isFallback: z.boolean().default(false),
});
export type ParkFactorData = z.infer<typeof ParkFactorData>;

export interface ParkFactorProvider {
  getParkFactor(venueId: string, season: number): Promise<ParkFactorData | null>;
}

// ---------------------------------------------------------------------------
// Results
// ---------------------------------------------------------------------------

export const GameResultData = z.object({
  gameId: z.string(),
  homeScore: z.number().int(),
  awayScore: z.number().int(),
  finalStatus: z.enum(['final', 'cancelled', 'postponed']),
  officialAt: z.date(),
});
export type GameResultData = z.infer<typeof GameResultData>;

export interface ResultsProvider {
  getResult(gameId: string): Promise<z.infer<ReturnType<typeof ProviderResult<typeof GameResultData>>> | null>;
}
