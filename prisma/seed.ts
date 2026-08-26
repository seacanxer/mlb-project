/**
 * prisma/seed.ts
 *
 * Seeds the database with:
 * - Model definitions (ML_COMBO_V2, OU_UNIFIED)
 * - Default config version
 * - Demo teams, venues, persons
 * - 12 demo fixture games, snapshots, and park factors
 */

import { PrismaClient } from '@prisma/client';
import { DEFAULT_CONFIG, DEFAULT_OU_TOTALS_CONFIG } from '../lib/config/modelConfig';
import { DEMO_FIXTURES } from '../lib/fixtures/demoFixtures';
import { computeEra } from '../lib/utils/innings';
import crypto from 'crypto';

const prisma = new PrismaClient();

function cksum(data: unknown) {
  return crypto.createHash('sha256').update(JSON.stringify(data)).digest('hex').slice(0, 16);
}

async function main() {
  console.log('🌱 Seeding database...');

  // ---------------------------------------------------------------------------
  // Model definitions
  // ---------------------------------------------------------------------------
  await prisma.modelDefinition.upsert({
    where: { id: 'ML_COMBO_V2' },
    create: { id: 'ML_COMBO_V2', name: 'Moneyline Combo Score', version: '2.1', description: 'Moneyline Combo Score v2.1 — deterministic scoring with explicit confidence caps.', isActive: true },
    update: { version: '2.1', description: 'Moneyline Combo Score v2.1 — deterministic scoring with explicit confidence caps.' },
  });
  await prisma.modelDefinition.upsert({
    where: { id: 'OU_UNIFIED' },
    create: { id: 'OU_UNIFIED', name: 'Unified MLB Totals', version: '4.0', description: 'Single market-anchored offense and pitching totals model. Experimental and not calibrated.', isActive: true },
    update: { version: '4.0', isActive: true },
  });
  await prisma.modelDefinition.updateMany({
    where: { id: { in: ['OU_V2_3', 'OU_V3'] } },
    data: { isActive: false },
  });

  // ---------------------------------------------------------------------------
  // Default config version
  // ---------------------------------------------------------------------------
  const existingConfig = await prisma.modelConfigVersion.findFirst({
    where: { modelId: 'ML_COMBO_V2', semver: DEFAULT_CONFIG.version },
  });
  let configVersionId: string;
  if (!existingConfig) {
    const cfg = await prisma.modelConfigVersion.create({
      data: {
        modelId: 'ML_COMBO_V2',
        semver: DEFAULT_CONFIG.version,
        configJson: JSON.stringify(DEFAULT_CONFIG),
        isActive: true,
        createdBy: 'seed',
      },
    });
    configVersionId = cfg.id;
  } else {
    configVersionId = existingConfig.id;
  }

  const existingOuConfig = await prisma.modelConfigVersion.findFirst({
    where: { modelId: 'OU_UNIFIED', semver: DEFAULT_OU_TOTALS_CONFIG.version },
  });
  if (!existingOuConfig) {
    await prisma.modelConfigVersion.create({
      data: {
        modelId: 'OU_UNIFIED',
        semver: DEFAULT_OU_TOTALS_CONFIG.version,
        configJson: JSON.stringify(DEFAULT_OU_TOTALS_CONFIG),
        isActive: true,
        createdBy: 'seed',
      },
    });
  }

  console.log(`✓ Model definitions and config version (${DEFAULT_CONFIG.version}) created.`);

  // ---------------------------------------------------------------------------
  // Seed fixtures
  // ---------------------------------------------------------------------------
  for (const fixture of DEMO_FIXTURES) {
    const { game, homeStarter, awayStarter, homeTeamStats, awayTeamStats, odds, parkFactor } = fixture;

    // Teams
    await prisma.team.upsert({
      where: { id: game.homeTeamId },
      create: { id: game.homeTeamId, name: game.homeTeamName, abbreviation: game.homeTeamId.slice(0, 3), city: 'Demo', leagueId: 104, divisionId: 201 },
      update: { name: game.homeTeamName },
    });
    await prisma.team.upsert({
      where: { id: game.awayTeamId },
      create: { id: game.awayTeamId, name: game.awayTeamName, abbreviation: game.awayTeamId.slice(0, 3), city: 'Demo', leagueId: 103, divisionId: 200 },
      update: { name: game.awayTeamName },
    });

    // Venue
    await prisma.venue.upsert({
      where: { id: game.venueId },
      create: { id: game.venueId, name: game.venueName, city: 'Demo City' },
      update: {},
    });

    // Persons
    await prisma.person.upsert({
      where: { id: homeStarter.personId },
      create: { id: homeStarter.personId, fullName: homeStarter.name, position: 'P' },
      update: {},
    });
    await prisma.person.upsert({
      where: { id: awayStarter.personId },
      create: { id: awayStarter.personId, fullName: awayStarter.name, position: 'P' },
      update: {},
    });

    // Game
    await prisma.game.upsert({
      where: { id: game.id },
      create: {
        id: game.id,
        date: game.date,
        startTimeUtc: new Date(game.startTimeUtc),
        status: 'scheduled',
        homeTeamId: game.homeTeamId,
        awayTeamId: game.awayTeamId,
        venueId: game.venueId,
        season: game.season,
      },
      update: {},
    });

    // Park factor snapshot
    const pfExists = await prisma.parkFactorSnapshot.findFirst({
      where: { venueId: parkFactor.venueId, season: parkFactor.season },
    });
    if (!pfExists) {
      await prisma.parkFactorSnapshot.create({
        data: {
          venueId: parkFactor.venueId,
          season: parkFactor.season,
          factor: parkFactor.factor,
          source: 'demo-fixtures-2025',
          isFallback: parkFactor.isFallback,
        },
      });
    }

    // Pitcher snapshots
    const homeSnap = await prisma.pitcherSnapshot.create({
      data: {
        personId: homeStarter.personId,
        season: game.season,
        era: homeStarter.seasonEra,
        whip: homeStarter.seasonWhip,
        inningsPitched: parseFloat((homeStarter.outsRecorded / 3).toFixed(1)),
        outsRecorded: homeStarter.outsRecorded,
        gamesStarted: homeStarter.gamesStarted,
        earnedRuns: Math.round((homeStarter.seasonEra * homeStarter.outsRecorded) / 27),
        walks: 30,
        strikeouts: 120,
        sourceProvider: 'demo',
        retrievedAt: new Date(),
        freshnessState: 'fresh',
      },
    });
    const awaySnap = await prisma.pitcherSnapshot.create({
      data: {
        personId: awayStarter.personId,
        season: game.season,
        era: awayStarter.seasonEra,
        whip: awayStarter.seasonWhip,
        inningsPitched: parseFloat((awayStarter.outsRecorded / 3).toFixed(1)),
        outsRecorded: awayStarter.outsRecorded,
        gamesStarted: awayStarter.gamesStarted,
        earnedRuns: Math.round((awayStarter.seasonEra * awayStarter.outsRecorded) / 27),
        walks: 28,
        strikeouts: 130,
        sourceProvider: 'demo',
        retrievedAt: new Date(),
        freshnessState: 'fresh',
      },
    });

    // Game logs
    for (const log of homeStarter.gameLogs) {
      const gameEra = computeEra(log.earnedRuns, log.outsRecorded);
      await prisma.pitcherGameLogStart.create({
        data: {
          personId: homeStarter.personId,
          gameDate: log.gameDate,
          season: game.season,
          earnedRuns: log.earnedRuns,
          outsRecorded: log.outsRecorded,
          gameEra,
          isGoodStart: gameEra < 4.0,
          sourceProvider: 'demo',
          retrievedAt: new Date(),
        },
      });
    }
    for (const log of awayStarter.gameLogs) {
      const gameEra = computeEra(log.earnedRuns, log.outsRecorded);
      await prisma.pitcherGameLogStart.create({
        data: {
          personId: awayStarter.personId,
          gameDate: log.gameDate,
          season: game.season,
          earnedRuns: log.earnedRuns,
          outsRecorded: log.outsRecorded,
          gameEra,
          isGoodStart: gameEra < 4.0,
          sourceProvider: 'demo',
          retrievedAt: new Date(),
        },
      });
    }

    // Team snapshots
    await prisma.teamSnapshot.create({
      data: {
        teamId: game.homeTeamId,
        season: game.season,
        avg: homeTeamStats.avg,
        ops: homeTeamStats.ops,
        runsPerGame: homeTeamStats.runsPerGame,
        wins: homeTeamStats.last10Wins,
        losses: homeTeamStats.last10Losses,
        last10Wins: homeTeamStats.last10Wins,
        last10Losses: homeTeamStats.last10Losses,
        currentStreak: homeTeamStats.winStreak > 0 ? homeTeamStats.winStreak : -homeTeamStats.lossStreak,
        sourceProvider: 'demo',
        retrievedAt: new Date(),
        freshnessState: 'fresh',
      },
    });
    await prisma.teamSnapshot.create({
      data: {
        teamId: game.awayTeamId,
        season: game.season,
        avg: awayTeamStats.avg,
        ops: awayTeamStats.ops,
        runsPerGame: awayTeamStats.runsPerGame,
        wins: awayTeamStats.last10Wins,
        losses: awayTeamStats.last10Losses,
        last10Wins: awayTeamStats.last10Wins,
        last10Losses: awayTeamStats.last10Losses,
        currentStreak: awayTeamStats.winStreak > 0 ? awayTeamStats.winStreak : -awayTeamStats.lossStreak,
        sourceProvider: 'demo',
        retrievedAt: new Date(),
        freshnessState: 'fresh',
      },
    });

    // Market snapshot
    await prisma.marketSnapshot.create({
      data: {
        gameId: game.id,
        provider: odds.isStale ? 'demo-stale' : 'demo',
        retrievedAt: odds.isStale ? new Date(Date.now() - 6 * 3600_000) : new Date(),
        moneylineHome: odds.moneylineHomeDecimal,
        moneylineAway: odds.moneylineAwayDecimal,
        moneylineHomeOrig: odds.moneylineHomeOrig,
        moneylineAwayOrig: odds.moneylineAwayOrig,
        totalLine: odds.totalLine,
        totalOverDecimal: odds.totalOverDecimal,
        totalUnderDecimal: odds.totalUnderDecimal,
        freshnessState: odds.isStale ? 'stale' : 'fresh',
      },
    });

    // Probable starter observations
    await prisma.probableStarterObservation.create({
      data: {
        gameId: game.id,
        personId: homeStarter.personId,
        side: 'home',
        confirmationStatus: homeStarter.confirmed ? 'confirmed' : 'conflicting',
        gamesStarted: homeStarter.gamesStarted,
        roleLabel: homeStarter.role,
        retrievedAt: new Date(),
        sourceProvider: 'demo',
      },
    });
    await prisma.probableStarterObservation.create({
      data: {
        gameId: game.id,
        personId: awayStarter.personId,
        side: 'away',
        confirmationStatus: awayStarter.confirmed ? 'confirmed' : 'conflicting',
        gamesStarted: awayStarter.gamesStarted,
        roleLabel: awayStarter.role,
        retrievedAt: new Date(),
        sourceProvider: 'demo',
      },
    });

    console.log(`  ✓ Fixture ${fixture.scenario}: ${fixture.label}`);
  }

  console.log('\n✅ Seed complete.');
}

main()
  .catch((e) => { console.error(e); process.exit(1); })
  .finally(() => prisma.$disconnect());
