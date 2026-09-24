import { PrismaClient } from '@prisma/client';
import * as fs from 'fs';
import * as path from 'path';

const connectionUrl = process.env.DIRECT_URL || process.env.DATABASE_URL;
const prisma = new PrismaClient({
  datasources: {
    db: {
      url: connectionUrl
    }
  }
});


async function main() {
  const forecasts = await prisma.forecast.findMany({
    include: {
      settlement: {
        include: {
          gameResult: true,
        }
      },
      modelRun: {
        include: {
          model: true,
          game: {
            include: {
              homeTeam: true,
              awayTeam: true,
              venue: true,
            }
          }
        }
      }
    },
    orderBy: {
      lockedAt: 'asc'
    }
  });

  console.log(`Loaded ${forecasts.length} forecasts from Postgres`);

  const records = forecasts.map((f, idx) => {
    const mr = f.modelRun;
    const g = mr.game;
    const s = f.settlement;
    const gr = s?.gameResult;

    let outputParsed: any = {};
    try {
      outputParsed = JSON.parse(mr.outputJson);
    } catch {}

    const market = mr.modelId === 'ML_COMBO_V2' ? 'moneyline' : 'totals';
    const outcome = s ? s.outcome : 'pending';
    const decimalOdds = f.marketPrice ?? outputParsed.candidateDecimalOdds ?? outputParsed.selectedPrice ?? null;
    
    // Calculate profit units
    let profitUnits: number | null = null;
    if (outcome === 'win' && decimalOdds != null) {
      profitUnits = Number((decimalOdds - 1).toFixed(4));
    } else if (outcome === 'loss') {
      profitUnits = -1.0;
    } else if (outcome === 'push' || outcome === 'void') {
      profitUnits = 0.0;
    }

    // Pick description
    let pickLabel = '';
    if (market === 'moneyline') {
      const teamAbbr = f.selectedSide === 'home' ? g.homeTeam.abbreviation : g.awayTeam.abbreviation;
      const teamName = f.selectedSide === 'home' ? g.homeTeam.name : g.awayTeam.name;
      pickLabel = `${teamAbbr} ML (${teamName})`;
    } else {
      pickLabel = `${f.selectedSide?.toUpperCase()} ${f.marketLine ?? outputParsed.marketLine ?? ''}`;
    }

    return {
      index: idx + 1,
      forecastId: f.id,
      lockedAt: f.lockedAt.toISOString(),
      gameId: g.id,
      gameDate: g.date,
      matchup: `${g.awayTeam.abbreviation} @ ${g.homeTeam.abbreviation}`,
      homeTeam: g.homeTeam.name,
      awayTeam: g.awayTeam.name,
      homeAbbr: g.homeTeam.abbreviation,
      awayAbbr: g.awayTeam.abbreviation,
      venue: g.venue.name,
      modelId: mr.modelId,
      market,
      tier: f.finalState,
      selectedSide: f.selectedSide,
      marketLine: f.marketLine,
      decimalOdds,
      rawScore: mr.rawScore,
      rawGap: mr.rawGap,
      fairDecimal: outputParsed.fairDecimal ?? null,
      edge: outputParsed.fairDecimal && decimalOdds ? Number(((decimalOdds / outputParsed.fairDecimal - 1) * 100).toFixed(2)) : null,
      projectedTotal: outputParsed.projectedTotal ?? null,
      pickLabel,
      status: outcome,
      homeScore: gr?.homeScore ?? null,
      awayScore: gr?.awayScore ?? null,
      scoreStr: gr ? `${gr.awayScore}-${gr.homeScore}` : null,
      settledAt: s?.settledAt ? s.settledAt.toISOString() : null,
      profitUnits,
      gradeNotes: s?.gradeNotes ?? null,
    };
  });

  const settled = records.filter(r => r.status !== 'pending');
  const pending = records.filter(r => r.status === 'pending');

  const wins = settled.filter(r => r.status === 'win').length;
  const losses = settled.filter(r => r.status === 'loss').length;
  const pushes = settled.filter(r => r.status === 'push').length;
  const voids = settled.filter(r => r.status === 'void').length;
  const totalProfit = settled.reduce((sum, r) => sum + (r.profitUnits ?? 0), 0);
  const unitsStaked = settled.filter(r => r.status !== 'void').length;
  const roiPct = unitsStaked > 0 ? (totalProfit / unitsStaked) * 100 : 0;
  const winRatePct = (wins + losses) > 0 ? (wins / (wins + losses)) * 100 : 0;

  // Breakdown by Market
  const markets = ['moneyline', 'totals'];
  const marketPerformance = markets.map(m => {
    const subset = settled.filter(r => r.market === m);
    const mWins = subset.filter(r => r.status === 'win').length;
    const mLosses = subset.filter(r => r.status === 'loss').length;
    const mPushes = subset.filter(r => r.status === 'push').length;
    const mProfit = subset.reduce((sum, r) => sum + (r.profitUnits ?? 0), 0);
    const mStaked = subset.length;
    const mRoi = mStaked > 0 ? (mProfit / mStaked) * 100 : 0;
    const mWinRate = (mWins + mLosses) > 0 ? (mWins / (mWins + mLosses)) * 100 : 0;
    const oddsTotal = subset.reduce((sum, r) => sum + (r.decimalOdds ?? 0), 0);

    return {
      market: m,
      bets: subset.length,
      wins: mWins,
      losses: mLosses,
      pushes: mPushes,
      win_rate_pct: Number(mWinRate.toFixed(1)),
      profit_units: Number(mProfit.toFixed(2)),
      roi_pct: Number(mRoi.toFixed(1)),
      avg_odds: subset.length > 0 ? Number((oddsTotal / subset.length).toFixed(3)) : 0,
    };
  });

  // Breakdown by Tier / Final State
  const tiers = Array.from(new Set(records.map(r => r.tier)));
  const tierPerformance = tiers.map(t => {
    const subset = settled.filter(r => r.tier === t);
    const tWins = subset.filter(r => r.status === 'win').length;
    const tLosses = subset.filter(r => r.status === 'loss').length;
    const tPushes = subset.filter(r => r.status === 'push').length;
    const tProfit = subset.reduce((sum, r) => sum + (r.profitUnits ?? 0), 0);
    const tStaked = subset.length;
    const tRoi = tStaked > 0 ? (tProfit / tStaked) * 100 : 0;
    const tWinRate = (tWins + tLosses) > 0 ? (tWins / (tWins + tLosses)) * 100 : 0;

    return {
      tier: t,
      market: subset[0]?.market ?? 'unknown',
      total_bets: records.filter(r => r.tier === t).length,
      settled_bets: subset.length,
      wins: tWins,
      losses: tLosses,
      pushes: tPushes,
      win_rate_pct: Number(tWinRate.toFixed(1)),
      profit_units: Number(tProfit.toFixed(2)),
      roi_pct: Number(tRoi.toFixed(1)),
    };
  }).sort((a, b) => b.settled_bets - a.settled_bets);

  const snapshot = {
    generated_at: new Date().toISOString(),
    date_range: {
      start: settled[0]?.gameDate,
      end: settled[settled.length - 1]?.gameDate,
    },
    summary: {
      total_forecasts: records.length,
      settled_picks: settled.length,
      pending_picks: pending.length,
      wins,
      losses,
      pushes,
      voids,
      win_rate_pct: Number(winRatePct.toFixed(1)),
      profit_units: Number(totalProfit.toFixed(2)),
      roi_pct: Number(roiPct.toFixed(1)),
      unit_size: 1.0,
    },
    market_performance: marketPerformance,
    tier_performance: tierPerformance,
    settled,
    pending,
  };

  const outDir = path.join(process.cwd(), 'reports');
  if (!fs.existsSync(outDir)) {
    fs.mkdirSync(outDir, { recursive: true });
  }

  const outPath = path.join(outDir, 'mlb_tracker_snapshot.json');
  fs.writeFileSync(outPath, JSON.stringify(snapshot, null, 2), 'utf-8');
  console.log(`Saved snapshot to ${outPath}`);
  console.log('Summary:', snapshot.summary);
  console.log('Market Performance:', snapshot.market_performance);
  console.log('Tier Performance:', snapshot.tier_performance);
}

main()
  .catch(console.error)
  .finally(() => prisma.$disconnect());
