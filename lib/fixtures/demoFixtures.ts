/**
 * lib/fixtures/demoFixtures.ts
 *
 * 12 deterministic demo fixtures covering every required scenario.
 * These fixtures are used when real data is unavailable.
 *
 * Fixture index:
 *  1. Valid T1 Moneyline candidate
 *  2. T2 candidate
 *  3. Negative ERA-gap SKIP
 *  4. Starter GS=0 SKIP
 *  5. Fewer-than-five-starts SKIP
 *  6. Stale odds NEEDS_DATA
 *  7. O/U strong Over gap
 *  8. O/U risky Under gap
 *  9. O/U NO_BET near zero
 * 10. O/U adjustment capped at +3.0
 * 11. Starter change invalidation
 * 12. Push settlement on integer total
 */

export interface DemoGame {
  id: string;
  label: string;
  description: string;
  date: string;
  startTimeUtc: string;
  homeTeamId: string;
  homeTeamName: string;
  awayTeamId: string;
  awayTeamName: string;
  venueId: string;
  venueName: string;
  season: number;
}

export interface DemoStarter {
  personId: string;
  name: string;
  side: 'home' | 'away';
  confirmed: boolean;
  gamesStarted: number;
  role: 'starter' | 'reliever' | 'opener';
  seasonEra: number;
  seasonWhip: number;
  outsRecorded: number;
  gameLogs: { earnedRuns: number; outsRecorded: number; gameDate: string }[];
}

export interface DemoTeamStats {
  teamId: string;
  avg: number;
  ops: number;
  runsPerGame: number;
  last10Wins: number;
  last10Losses: number;
  winStreak: number;
  lossStreak: number;
}

export interface DemoOdds {
  moneylineHomeDecimal: number;
  moneylineAwayDecimal: number;
  moneylineHomeOrig: string;
  moneylineAwayOrig: string;
  totalLine: number;
  totalOverDecimal: number;
  totalUnderDecimal: number;
  isStale: boolean;
}

export interface DemoParkFactor {
  venueId: string;
  factor: number;
  season: number;
  isFallback: boolean;
}

export interface DemoFixture {
  scenario: number;
  label: string;
  description: string;
  game: DemoGame;
  homeStarter: DemoStarter;
  awayStarter: DemoStarter;
  homeTeamStats: DemoTeamStats;
  awayTeamStats: DemoTeamStats;
  odds: DemoOdds;
  parkFactor: DemoParkFactor;
  expectedMlState: string;
  expectedOuState: string;
  notes: string;
}

// ---------------------------------------------------------------------------
// Helper builders
// ---------------------------------------------------------------------------

function makeStarter(
  personId: string,
  name: string,
  side: 'home' | 'away',
  opts: Partial<DemoStarter> = {}
): DemoStarter {
  return {
    personId,
    name,
    side,
    confirmed: true,
    gamesStarted: 18,
    role: 'starter',
    seasonEra: 3.50,
    seasonWhip: 1.20,
    outsRecorded: 200,
    gameLogs: [
      { earnedRuns: 1, outsRecorded: 18, gameDate: '2025-07-15' },
      { earnedRuns: 2, outsRecorded: 18, gameDate: '2025-07-09' },
      { earnedRuns: 1, outsRecorded: 21, gameDate: '2025-07-03' },
      { earnedRuns: 0, outsRecorded: 24, gameDate: '2025-06-27' },
      { earnedRuns: 1, outsRecorded: 18, gameDate: '2025-06-21' },
    ],
    ...opts,
  };
}

function makeTeamStats(teamId: string, opts: Partial<DemoTeamStats> = {}): DemoTeamStats {
  return {
    teamId,
    avg: 0.265,
    ops: 0.770,
    runsPerGame: 4.6,
    last10Wins: 7,
    last10Losses: 3,
    winStreak: 2,
    lossStreak: 0,
    ...opts,
  };
}

function makeOdds(homeOrig: string, awayOrig: string, line: number, opts: Partial<DemoOdds> = {}): DemoOdds {
  const parseAmerican = (s: string) => {
    const n = parseInt(s);
    return n < 0 ? 1 + 100 / Math.abs(n) : 1 + n / 100;
  };
  return {
    moneylineHomeDecimal: parseAmerican(homeOrig),
    moneylineAwayDecimal: parseAmerican(awayOrig),
    moneylineHomeOrig: homeOrig,
    moneylineAwayOrig: awayOrig,
    totalLine: line,
    totalOverDecimal: 1.91,
    totalUnderDecimal: 1.91,
    isStale: false,
    ...opts,
  };
}

function makeGame(id: string, label: string, date: string = '2025-08-25'): DemoGame {
  return {
    id,
    label,
    description: label,
    date,
    startTimeUtc: `${date}T23:05:00Z`,
    homeTeamId: `HOME_${id}`,
    homeTeamName: 'Home Team',
    awayTeamId: `AWAY_${id}`,
    awayTeamName: 'Away Team',
    venueId: `VENUE_${id}`,
    venueName: 'Demo Stadium',
    season: 2025,
  };
}

// ---------------------------------------------------------------------------
// 12 Fixtures
// ---------------------------------------------------------------------------

export const DEMO_FIXTURES: DemoFixture[] = [
  // 1. Valid T1 Moneyline candidate
  {
    scenario: 1,
    label: 'T1 — Strong Moneyline Candidate',
    description: 'Away team ace has 2.00+ ERA gap, elite offense, 5 good starts, at-fair market price.',
    game: { ...makeGame('DEMO_01', 'NYY @ BOS'), homeTeamName: 'Boston Red Sox', awayTeamName: 'New York Yankees' },
    homeStarter: makeStarter('P_HOME_01', 'Home Starter', 'home', { seasonEra: 5.20, outsRecorded: 185 }),
    awayStarter: makeStarter('P_AWAY_01', 'Away Ace', 'away', { seasonEra: 2.85, outsRecorded: 210 }),
    homeTeamStats: makeTeamStats('HOME_DEMO_01', { avg: 0.250, ops: 0.740 }),
    awayTeamStats: makeTeamStats('AWAY_DEMO_01', { avg: 0.275, ops: 0.790, last10Wins: 8, winStreak: 3 }),
    odds: makeOdds('-140', '+120', 8.5),
    parkFactor: { venueId: 'VENUE_DEMO_01', factor: 1.02, season: 2025, isFallback: false },
    expectedMlState: 'T1',
    expectedOuState: 'NO_BET',
    notes: 'ERA gap ~2.35 → 35 pts; offense elite → 25; 5 good starts → 20; alignment atFair → 10; form 10 = 100',
  },

  // 2. T2 candidate
  {
    scenario: 2,
    label: 'T2 — Watchlist Candidate',
    description: 'Modest ERA gap of 1.30, good offense, 3 good starts, slight market premium.',
    game: { ...makeGame('DEMO_02', 'LAD @ SF'), homeTeamName: 'San Francisco Giants', awayTeamName: 'Los Angeles Dodgers' },
    homeStarter: makeStarter('P_HOME_02', 'Home Starter', 'home', { seasonEra: 4.50 }),
    awayStarter: makeStarter('P_AWAY_02', 'Away Starter', 'away', {
      seasonEra: 3.20,
      gameLogs: [
        { earnedRuns: 1, outsRecorded: 18, gameDate: '2025-07-15' },
        { earnedRuns: 2, outsRecorded: 18, gameDate: '2025-07-09' },
        { earnedRuns: 1, outsRecorded: 18, gameDate: '2025-07-03' },
        { earnedRuns: 3, outsRecorded: 15, gameDate: '2025-06-27' }, // bad start
        { earnedRuns: 3, outsRecorded: 12, gameDate: '2025-06-21' }, // bad start
      ],
    }),
    homeTeamStats: makeTeamStats('HOME_DEMO_02', { avg: 0.248 }),
    awayTeamStats: makeTeamStats('AWAY_DEMO_02', { avg: 0.258, ops: 0.755, last10Wins: 6, winStreak: 1 }),
    odds: makeOdds('-165', '+140', 8.0),
    parkFactor: { venueId: 'VENUE_DEMO_02', factor: 0.97, season: 2025, isFallback: false },
    expectedMlState: 'T2',
    expectedOuState: 'NO_BET',
    notes: 'ERA gap 1.30 → 21 pts; avg .258 good → 20; 3 good starts → 12; alignment diff < 0.20 → 8; form 8 = 69 → T2',
  },

  // 3. Negative ERA-gap SKIP
  {
    scenario: 3,
    label: 'SKIP — Negative ERA Gap',
    description: 'Candidate starter has HIGHER ERA than opponent. ERA gap <= 0 → immediate SKIP.',
    game: { ...makeGame('DEMO_03', 'ATL @ MIA'), homeTeamName: 'Miami Marlins', awayTeamName: 'Atlanta Braves' },
    homeStarter: makeStarter('P_HOME_03', 'Home Ace', 'home', { seasonEra: 2.50 }),
    awayStarter: makeStarter('P_AWAY_03', 'Away Starter', 'away', { seasonEra: 4.80 }),
    homeTeamStats: makeTeamStats('HOME_DEMO_03'),
    awayTeamStats: makeTeamStats('AWAY_DEMO_03'),
    odds: makeOdds('+110', '-130', 9.0),
    parkFactor: { venueId: 'VENUE_DEMO_03', factor: 1.00, season: 2025, isFallback: false },
    expectedMlState: 'SKIP',
    expectedOuState: 'NO_BET',
    notes: 'Away ERA 4.80 > Home ERA 2.50 → EraGap < 0 for away team → SKIP',
  },

  // 4. Starter GS=0 SKIP
  {
    scenario: 4,
    label: 'SKIP — Starter GS=0 (Reliever/Opener)',
    description: 'Probable starter has zero games started; classified as reliever.',
    game: { ...makeGame('DEMO_04', 'CHC @ STL'), homeTeamName: 'St. Louis Cardinals', awayTeamName: 'Chicago Cubs' },
    homeStarter: makeStarter('P_HOME_04', 'Home Starter', 'home', { seasonEra: 3.80 }),
    awayStarter: makeStarter('P_AWAY_04', 'Reliever Bob', 'away', {
      seasonEra: 2.10,
      gamesStarted: 0,
      role: 'reliever',
      outsRecorded: 55,
    }),
    homeTeamStats: makeTeamStats('HOME_DEMO_04'),
    awayTeamStats: makeTeamStats('AWAY_DEMO_04'),
    odds: makeOdds('-120', '+100', 8.5),
    parkFactor: { venueId: 'VENUE_DEMO_04', factor: 1.00, season: 2025, isFallback: false },
    expectedMlState: 'SKIP',
    expectedOuState: 'NO_BET',
    notes: 'GS=0 and role=reliever → STARTER_GS_ZERO and STARTER_IS_RELIEVER hard gates',
  },

  // 5. Fewer-than-five-starts SKIP
  {
    scenario: 5,
    label: 'SKIP — Insufficient Game Log (< 5 Starts)',
    description: 'Pitcher only has 3 recent starts in log. Model requires 5.',
    game: { ...makeGame('DEMO_05', 'HOU @ OAK'), homeTeamName: 'Oakland Athletics', awayTeamName: 'Houston Astros' },
    homeStarter: makeStarter('P_HOME_05', 'Home Starter', 'home', { seasonEra: 4.20 }),
    awayStarter: makeStarter('P_AWAY_05', 'Rookie Pitcher', 'away', {
      seasonEra: 2.80,
      gamesStarted: 3,
      outsRecorded: 180,
      gameLogs: [
        { earnedRuns: 1, outsRecorded: 18, gameDate: '2025-07-15' },
        { earnedRuns: 0, outsRecorded: 21, gameDate: '2025-07-09' },
        { earnedRuns: 2, outsRecorded: 18, gameDate: '2025-07-03' },
      ],
    }),
    homeTeamStats: makeTeamStats('HOME_DEMO_05'),
    awayTeamStats: makeTeamStats('AWAY_DEMO_05'),
    odds: makeOdds('-115', '-105', 8.0),
    parkFactor: { venueId: 'VENUE_DEMO_05', factor: 1.00, season: 2025, isFallback: false },
    expectedMlState: 'SKIP',
    expectedOuState: 'NO_BET',
    notes: 'Only 3 game log entries → INSUFFICIENT_GAME_LOG hard gate',
  },

  // 6. Stale odds NEEDS_DATA
  {
    scenario: 6,
    label: 'NEEDS_DATA — Stale Odds',
    description: 'Market odds are stale (not refreshed for 4+ hours). Cannot produce eligible forecast.',
    game: { ...makeGame('DEMO_06', 'SEA @ MIN'), homeTeamName: 'Minnesota Twins', awayTeamName: 'Seattle Mariners' },
    homeStarter: makeStarter('P_HOME_06', 'Home Starter', 'home', { seasonEra: 4.10 }),
    awayStarter: makeStarter('P_AWAY_06', 'Away Starter', 'away', { seasonEra: 2.40 }),
    homeTeamStats: makeTeamStats('HOME_DEMO_06'),
    awayTeamStats: makeTeamStats('AWAY_DEMO_06'),
    odds: makeOdds('-140', '+120', 8.5, { isStale: true }),
    parkFactor: { venueId: 'VENUE_DEMO_06', factor: 1.00, season: 2025, isFallback: false },
    expectedMlState: 'SKIP',
    expectedOuState: 'NO_BET',
    notes: 'isStale=true → ODDS_MISSING_OR_STALE / OU_STALE_ODDS hard gates',
  },

  // 7. O/U strong Over gap
  {
    scenario: 7,
    label: 'OVER — Strong Model Gap',
    description: 'High-scoring offenses, both pitchers trending worse than season ERA. Park factor hitter-friendly. Gap >= 0.75.',
    game: { ...makeGame('DEMO_07', 'COL @ TEX'), homeTeamName: 'Texas Rangers', awayTeamName: 'Colorado Rockies' },
    homeStarter: makeStarter('P_HOME_07', 'Home Starter', 'home', {
      seasonEra: 4.20,
      gameLogs: [
        { earnedRuns: 4, outsRecorded: 15, gameDate: '2025-07-15' },
        { earnedRuns: 5, outsRecorded: 12, gameDate: '2025-07-09' },
        { earnedRuns: 3, outsRecorded: 15, gameDate: '2025-07-03' },
        { earnedRuns: 4, outsRecorded: 15, gameDate: '2025-06-27' },
        { earnedRuns: 4, outsRecorded: 12, gameDate: '2025-06-21' },
      ],
    }),
    awayStarter: makeStarter('P_AWAY_07', 'Away Starter', 'away', {
      seasonEra: 3.80,
      gameLogs: [
        { earnedRuns: 3, outsRecorded: 15, gameDate: '2025-07-15' },
        { earnedRuns: 4, outsRecorded: 15, gameDate: '2025-07-09' },
        { earnedRuns: 3, outsRecorded: 18, gameDate: '2025-07-03' },
        { earnedRuns: 4, outsRecorded: 12, gameDate: '2025-06-27' },
        { earnedRuns: 3, outsRecorded: 15, gameDate: '2025-06-21' },
      ],
    }),
    homeTeamStats: makeTeamStats('HOME_DEMO_07', { runsPerGame: 5.8 }),
    awayTeamStats: makeTeamStats('AWAY_DEMO_07', { runsPerGame: 5.5 }),
    odds: makeOdds('-105', '-115', 10.0, { totalLine: 10.0, totalOverDecimal: 1.90, totalUnderDecimal: 1.91 }),
    parkFactor: { venueId: 'VENUE_DEMO_07', factor: 1.10, season: 2025, isFallback: false },
    expectedMlState: 'SKIP',
    expectedOuState: 'OVER_STRONG_GAP',
    notes: 'High RPG offenses + pitchers worse than season ERA + hitter-friendly park → large positive gap',
  },

  // 8. O/U risky Under gap
  {
    scenario: 8,
    label: 'UNDER — Risky Signal',
    description: 'Pitcher-friendly park, dominant aces trending better than season ERA, low-scoring offenses.',
    game: { ...makeGame('DEMO_08', 'SD @ LAD'), homeTeamName: 'Los Angeles Dodgers', awayTeamName: 'San Diego Padres' },
    homeStarter: makeStarter('P_HOME_08', 'Home Ace', 'home', {
      seasonEra: 2.90,
      gameLogs: [
        { earnedRuns: 0, outsRecorded: 24, gameDate: '2025-07-15' },
        { earnedRuns: 1, outsRecorded: 24, gameDate: '2025-07-09' },
        { earnedRuns: 0, outsRecorded: 21, gameDate: '2025-07-03' },
        { earnedRuns: 1, outsRecorded: 21, gameDate: '2025-06-27' },
        { earnedRuns: 0, outsRecorded: 27, gameDate: '2025-06-21' },
      ],
    }),
    awayStarter: makeStarter('P_AWAY_08', 'Away Ace', 'away', {
      seasonEra: 3.10,
      gameLogs: [
        { earnedRuns: 0, outsRecorded: 21, gameDate: '2025-07-15' },
        { earnedRuns: 1, outsRecorded: 21, gameDate: '2025-07-09' },
        { earnedRuns: 0, outsRecorded: 24, gameDate: '2025-07-03' },
        { earnedRuns: 1, outsRecorded: 21, gameDate: '2025-06-27' },
        { earnedRuns: 0, outsRecorded: 24, gameDate: '2025-06-21' },
      ],
    }),
    homeTeamStats: makeTeamStats('HOME_DEMO_08', { runsPerGame: 3.8 }),
    awayTeamStats: makeTeamStats('AWAY_DEMO_08', { runsPerGame: 3.9 }),
    odds: makeOdds('-130', '+110', 7.0, { totalLine: 7.0, totalOverDecimal: 1.91, totalUnderDecimal: 1.88 }),
    parkFactor: { venueId: 'VENUE_DEMO_08', factor: 0.94, season: 2025, isFallback: false },
    expectedMlState: 'SKIP',
    expectedOuState: 'UNDER_RISKY',
    notes: 'Low RPG + aces better than season ERA + pitcher-friendly park → negative gap in -0.50 to -0.75 range',
  },

  // 9. O/U NO_BET near zero
  {
    scenario: 9,
    label: 'NO_BET — Gap Near Zero',
    description: 'Balanced game: league-average offense, neutral park, pitchers performing at season ERA.',
    game: { ...makeGame('DEMO_09', 'CLE @ DET'), homeTeamName: 'Detroit Tigers', awayTeamName: 'Cleveland Guardians' },
    homeStarter: makeStarter('P_HOME_09', 'Home Starter', 'home', {
      seasonEra: 4.00,
      gameLogs: [
        { earnedRuns: 2, outsRecorded: 15, gameDate: '2025-07-15' },
        { earnedRuns: 2, outsRecorded: 15, gameDate: '2025-07-09' },
        { earnedRuns: 2, outsRecorded: 15, gameDate: '2025-07-03' },
        { earnedRuns: 2, outsRecorded: 15, gameDate: '2025-06-27' },
        { earnedRuns: 2, outsRecorded: 15, gameDate: '2025-06-21' },
      ],
    }),
    awayStarter: makeStarter('P_AWAY_09', 'Away Starter', 'away', {
      seasonEra: 4.00,
      gameLogs: [
        { earnedRuns: 2, outsRecorded: 15, gameDate: '2025-07-15' },
        { earnedRuns: 2, outsRecorded: 15, gameDate: '2025-07-09' },
        { earnedRuns: 2, outsRecorded: 15, gameDate: '2025-07-03' },
        { earnedRuns: 2, outsRecorded: 15, gameDate: '2025-06-27' },
        { earnedRuns: 2, outsRecorded: 15, gameDate: '2025-06-21' },
      ],
    }),
    homeTeamStats: makeTeamStats('HOME_DEMO_09', { runsPerGame: 4.1 }),
    awayTeamStats: makeTeamStats('AWAY_DEMO_09', { runsPerGame: 4.1 }),
    odds: makeOdds('-110', '-110', 8.0, { totalLine: 8.0, totalOverDecimal: 1.91, totalUnderDecimal: 1.91 }),
    parkFactor: { venueId: 'VENUE_DEMO_09', factor: 1.00, season: 2025, isFallback: false },
    expectedMlState: 'SKIP',
    expectedOuState: 'NO_BET',
    notes: 'RPG at baseline (4.1), no PitchAdj (ERA = season), neutral park → gap ≈ 0 → NO_BET',
  },

  // 10. O/U adjustment capped at +3.0
  {
    scenario: 10,
    label: 'OVER — Adjustment Capped at +3.0',
    description: 'Very high-scoring offenses and extreme hitter-friendly park. Raw adjustment would exceed +3.0.',
    game: { ...makeGame('DEMO_10', 'COL @ CHC'), homeTeamName: 'Chicago Cubs', awayTeamName: 'Colorado Rockies' },
    homeStarter: makeStarter('P_HOME_10', 'Home Starter', 'home', {
      seasonEra: 5.50,
      gameLogs: [
        { earnedRuns: 5, outsRecorded: 12, gameDate: '2025-07-15' },
        { earnedRuns: 6, outsRecorded: 9, gameDate: '2025-07-09' },
        { earnedRuns: 4, outsRecorded: 12, gameDate: '2025-07-03' },
        { earnedRuns: 5, outsRecorded: 9, gameDate: '2025-06-27' },
        { earnedRuns: 5, outsRecorded: 12, gameDate: '2025-06-21' },
      ],
    }),
    awayStarter: makeStarter('P_AWAY_10', 'Away Starter', 'away', {
      seasonEra: 5.80,
      gameLogs: [
        { earnedRuns: 5, outsRecorded: 12, gameDate: '2025-07-15' },
        { earnedRuns: 4, outsRecorded: 12, gameDate: '2025-07-09' },
        { earnedRuns: 6, outsRecorded: 9, gameDate: '2025-07-03' },
        { earnedRuns: 5, outsRecorded: 12, gameDate: '2025-06-27' },
        { earnedRuns: 5, outsRecorded: 9, gameDate: '2025-06-21' },
      ],
    }),
    homeTeamStats: makeTeamStats('HOME_DEMO_10', { runsPerGame: 6.5 }),
    awayTeamStats: makeTeamStats('AWAY_DEMO_10', { runsPerGame: 6.2 }),
    odds: makeOdds('-110', '-110', 12.0, { totalLine: 12.0, totalOverDecimal: 1.90, totalUnderDecimal: 1.91 }),
    parkFactor: { venueId: 'VENUE_DEMO_10', factor: 1.12, season: 2025, isFallback: false },
    expectedMlState: 'SKIP',
    expectedOuState: 'OVER_STRONG_GAP',
    notes: 'rawTotalAdj > 3.0 → cap fires → EXTREME_PARK_ADJUSTMENT warning; capReached=true; gap = 3.0',
  },

  // 11. Starter change invalidation
  {
    scenario: 11,
    label: 'INVALIDATED — Starter Change',
    description: 'Original starter scratched and replaced. Affected model run invalidated; new run created after refresh.',
    game: { ...makeGame('DEMO_11', 'TOR @ NYY'), homeTeamName: 'New York Yankees', awayTeamName: 'Toronto Blue Jays' },
    homeStarter: makeStarter('P_HOME_11', 'Original Home Starter (Scratched)', 'home', {
      confirmed: false,
      seasonEra: 3.10,
    }),
    awayStarter: makeStarter('P_AWAY_11', 'Away Starter', 'away', { seasonEra: 4.80 }),
    homeTeamStats: makeTeamStats('HOME_DEMO_11'),
    awayTeamStats: makeTeamStats('AWAY_DEMO_11'),
    odds: makeOdds('-120', '+100', 8.5),
    parkFactor: { venueId: 'VENUE_DEMO_11', factor: 1.03, season: 2025, isFallback: false },
    expectedMlState: 'INVALIDATED',
    expectedOuState: 'INVALIDATED',
    notes: 'confirmed=false for home starter → STARTER_UNCONFIRMED → triggers invalidation workflow',
  },

  // 12. Push settlement on integer total
  {
    scenario: 12,
    label: 'PUSH — Integer Total Settlement',
    description: 'Game total lands exactly on the market line (e.g., 8 runs, line = 8.0). Forecast settles as PUSH.',
    game: { ...makeGame('DEMO_12', 'PHI @ WSH'), homeTeamName: 'Washington Nationals', awayTeamName: 'Philadelphia Phillies' },
    homeStarter: makeStarter('P_HOME_12', 'Home Starter', 'home', { seasonEra: 4.40 }),
    awayStarter: makeStarter('P_AWAY_12', 'Away Starter', 'away', { seasonEra: 3.20 }),
    homeTeamStats: makeTeamStats('HOME_DEMO_12'),
    awayTeamStats: makeTeamStats('AWAY_DEMO_12'),
    odds: makeOdds('-130', '+110', 8.0, { totalLine: 8.0, totalOverDecimal: 1.90, totalUnderDecimal: 1.91 }),
    parkFactor: { venueId: 'VENUE_DEMO_12', factor: 1.00, season: 2025, isFallback: false },
    expectedMlState: 'T2',
    expectedOuState: 'NO_BET',
    notes: 'Integer total line 8.0; actual result 5-3 = 8 → PUSH settlement; ROI not counted',
  },
];

export const DEMO_FIXTURE_MAP: Record<string, DemoFixture> = Object.fromEntries(
  DEMO_FIXTURES.map((f) => [f.game.id, f])
);
