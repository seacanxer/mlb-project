export interface PickerGameRequest {
  gameId: string;
  away: string;
  home: string;
  away_sp: string;
  home_sp: string;
  moneyline: string;
  total: string;
  model: string;
  venue: string;
  analysis: Record<string, unknown>;
}

export function starterForSide(game: any, side: 'away' | 'home') {
  const observations = game.probableStarterObservations || [];
  return observations.find((item: any) => item.side === side)
    ?? observations[side === 'away' ? 0 : 1]
    ?? null;
}

function parseRunOutput(run: any): Record<string, any> {
  if (!run?.outputJson) return {};
  if (typeof run.outputJson === 'object') return run.outputJson;
  try {
    return JSON.parse(run.outputJson);
  } catch {
    return {};
  }
}

export function analysisForGame(game: any) {
  const latest = new Map<string, any>();
  for (const run of game.modelRuns || []) {
    if (!latest.has(run.modelId)) latest.set(run.modelId, run);
  }
  const mlRun = latest.get('ML_COMBO_V2');
  const ouRun = latest.get('OU_UNIFIED');
  const ml = parseRunOutput(mlRun);
  const ou = parseRunOutput(ouRun);
  return {
    moneyline: mlRun ? {
      finalState: mlRun.finalState,
      rawScore: mlRun.rawScore,
      candidateTeamName: ml.candidateTeamName,
      candidateDecimalOdds: ml.candidateDecimalOdds,
      hardGates: ml.hardGates || [],
      warnings: ml.warnings || [],
    } : null,
    totals: ouRun ? {
      finalState: ouRun.finalState,
      rawGap: ouRun.rawGap,
      selectedSide: ou.selectedSide,
      selectedPrice: ou.selectedPrice,
      marketLine: ou.marketLine,
      dataQualityScore: ou.dataQualityScore,
      hardGates: ou.hardGates || [],
      warnings: ou.warnings || [],
    } : null,
  };
}

export function marketForGame(game: any) {
  const snap = game.marketSnapshots?.[0] || {};
  const awayCode = game.awayTeam?.abbreviation || 'AWAY';
  const homeCode = game.homeTeam?.abbreviation || 'HOME';
  const moneyline = snap.moneylineAway != null && snap.moneylineHome != null
    ? `${awayCode} ${snap.moneylineAway} / ${homeCode} ${snap.moneylineHome}`
    : 'Unavailable';
  const total = snap.totalLine != null
    ? `${snap.totalLine}${snap.totalOverDecimal != null && snap.totalUnderDecimal != null
      ? ` (O ${snap.totalOverDecimal} / U ${snap.totalUnderDecimal})`
      : ''}`
    : 'Unavailable';
  return { snap, moneyline, total };
}

export function buildPickerRequest(game: any, model: string): PickerGameRequest {
  const awayStarter = starterForSide(game, 'away');
  const homeStarter = starterForSide(game, 'home');
  const market = marketForGame(game);
  return {
    gameId: game.id,
    away: game.awayTeam?.name || 'Away',
    home: game.homeTeam?.name || 'Home',
    away_sp: awayStarter?.person?.fullName || awayStarter?.person?.name || 'TBD',
    home_sp: homeStarter?.person?.fullName || homeStarter?.person?.name || 'TBD',
    moneyline: market.moneyline,
    total: market.total,
    model,
    venue: game.venue?.name || '',
    analysis: analysisForGame(game),
  };
}
