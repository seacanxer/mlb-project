/**
 * lib/fixtures/parkFactors2026.ts
 *
 * Park factor data for all 30 MLB venues (2026 season).
 * Park factors represent the run-scoring environment of each ballpark
 * relative to a neutral park (1.00). Values above 1.00 favor hitters;
 * below 1.00 favor pitchers.
 *
 * Source: Derived from historical ESPN/FanGraphs park factor data.
 * These values are intentionally conservative and will be refined
 * as 2026 season data accumulates.
 */

export interface ParkFactorEntry {
  venueId: string;
  venueName: string;
  teamAbbreviation: string;
  factor: number;
  season: number;
  source: string;
}

export const PARK_FACTORS_2026: ParkFactorEntry[] = [
  // --- American League ---
  { venueId: '1',    venueName: 'Angel Stadium',                       teamAbbreviation: 'LAA', factor: 0.97, season: 2026, source: 'historical-avg' },
  { venueId: '2',    venueName: 'Oriole Park at Camden Yards',         teamAbbreviation: 'BAL', factor: 1.05, season: 2026, source: 'historical-avg' },
  { venueId: '3',    venueName: 'Fenway Park',                         teamAbbreviation: 'BOS', factor: 1.09, season: 2026, source: 'historical-avg' },
  { venueId: '4',    venueName: 'Rate Field',                          teamAbbreviation: 'CWS', factor: 1.05, season: 2026, source: 'historical-avg' },
  { venueId: '5',    venueName: 'Progressive Field',                   teamAbbreviation: 'CLE', factor: 0.96, season: 2026, source: 'historical-avg' },
  { venueId: '7',    venueName: 'Kauffman Stadium',                    teamAbbreviation: 'KC',  factor: 1.01, season: 2026, source: 'historical-avg' },
  { venueId: '12',   venueName: 'Tropicana Field',                     teamAbbreviation: 'TB',  factor: 0.91, season: 2026, source: 'historical-avg' },
  { venueId: '14',   venueName: 'Rogers Centre',                       teamAbbreviation: 'TOR', factor: 1.02, season: 2026, source: 'historical-avg' },
  { venueId: '680',  venueName: 'T-Mobile Park',                       teamAbbreviation: 'SEA', factor: 0.93, season: 2026, source: 'historical-avg' },
  { venueId: '2392', venueName: 'Daikin Park',                         teamAbbreviation: 'HOU', factor: 0.99, season: 2026, source: 'historical-avg' },
  { venueId: '2394', venueName: 'Comerica Park',                       teamAbbreviation: 'DET', factor: 0.96, season: 2026, source: 'historical-avg' },
  { venueId: '2529', venueName: 'Sutter Health Park',                  teamAbbreviation: 'ATH', factor: 1.00, season: 2026, source: 'historical-avg' },
  { venueId: '3312', venueName: 'Target Field',                        teamAbbreviation: 'MIN', factor: 1.03, season: 2026, source: 'historical-avg' },
  { venueId: '3313', venueName: 'Yankee Stadium',                      teamAbbreviation: 'NYY', factor: 1.11, season: 2026, source: 'historical-avg' },
  { venueId: '5325', venueName: 'Globe Life Field',                    teamAbbreviation: 'TEX', factor: 0.95, season: 2026, source: 'historical-avg' },

  // --- National League ---
  { venueId: '15',   venueName: 'Chase Field',                         teamAbbreviation: 'AZ',  factor: 1.08, season: 2026, source: 'historical-avg' },
  { venueId: '17',   venueName: 'Wrigley Field',                       teamAbbreviation: 'CHC', factor: 1.06, season: 2026, source: 'historical-avg' },
  { venueId: '19',   venueName: 'Coors Field',                         teamAbbreviation: 'COL', factor: 1.39, season: 2026, source: 'historical-avg' },
  { venueId: '22',   venueName: 'UNIQLO Field at Dodger Stadium',      teamAbbreviation: 'LAD', factor: 0.94, season: 2026, source: 'historical-avg' },
  { venueId: '31',   venueName: 'PNC Park',                            teamAbbreviation: 'PIT', factor: 0.92, season: 2026, source: 'historical-avg' },
  { venueId: '32',   venueName: 'American Family Field',               teamAbbreviation: 'MIL', factor: 1.04, season: 2026, source: 'historical-avg' },
  { venueId: '2395', venueName: 'Oracle Park',                         teamAbbreviation: 'SF',  factor: 0.83, season: 2026, source: 'historical-avg' },
  { venueId: '2602', venueName: 'Great American Ball Park',            teamAbbreviation: 'CIN', factor: 1.13, season: 2026, source: 'historical-avg' },
  { venueId: '2680', venueName: 'Petco Park',                          teamAbbreviation: 'SD',  factor: 0.90, season: 2026, source: 'historical-avg' },
  { venueId: '2681', venueName: 'Citizens Bank Park',                  teamAbbreviation: 'PHI', factor: 1.06, season: 2026, source: 'historical-avg' },
  { venueId: '2889', venueName: 'Busch Stadium',                       teamAbbreviation: 'STL', factor: 0.94, season: 2026, source: 'historical-avg' },
  { venueId: '3289', venueName: 'Citi Field',                          teamAbbreviation: 'NYM', factor: 0.93, season: 2026, source: 'historical-avg' },
  { venueId: '3309', venueName: 'Nationals Park',                      teamAbbreviation: 'WSH', factor: 1.02, season: 2026, source: 'historical-avg' },
  { venueId: '4169', venueName: 'loanDepot park',                      teamAbbreviation: 'MIA', factor: 0.87, season: 2026, source: 'historical-avg' },
  { venueId: '4705', venueName: 'Truist Park',                         teamAbbreviation: 'ATL', factor: 1.02, season: 2026, source: 'historical-avg' },
];
