import type { DetailedMatch, ForecastPick, Market } from './types';

export const FC_UI_VERSION = 'fc-market-board-v2';
export const PREDICTION_MARKETS: { key: Market; label: string }[] = [
  { key: '1x2', label: '1X2' }, { key: 'ah', label: 'Asian HDP' },
  { key: 'ou', label: 'O/U' }, { key: 'btts', label: 'BTTS' },
];

const REASONS: Record<string, string> = {
  LEAGUE_MODEL_UNAVAILABLE: 'Model untuk liga ini belum tersedia.',
  MODEL_UNAVAILABLE: 'Model liga belum berhasil dimuat.',
  TEAM_UNMATCHED: 'Identitas tim belum cocok dengan histori liga.',
  QUOTE_CAPTURE_FAILED: 'Odds pertandingan belum berhasil diverifikasi.',
  QUOTE_EXPIRED: 'Odds kedaluwarsa. Jalankan scan terbaru.',
  COMPLETE_MARKET_UNAVAILABLE: 'Pasangan odds pasar belum lengkap.',
  MODEL_NOT_VALIDATED: 'Model belum lolos validasi untuk Official.',
  RESCAN_REQUIRED: 'Jalankan scan untuk memperoleh analisis empat pasar.',
  STALE_TRAINING_DATA: 'Histori hasil terlalu lama; perbarui data liga.',
  ODDS_OUTSIDE_VALUE_RANGE: 'Odds di luar rentang value 1,60–2,50.',
  EV_BELOW_VALUE_THRESHOLD: 'EV belum mencapai 1%.',
  CONSERVATIVE_EV_BELOW_THRESHOLD: 'EV setelah penalti masih negatif.',
  TEAM_COVERAGE_MISSING: 'Histori tim belum cukup.',
  TEAM_LOW_COVERAGE: 'Sampel tim masih terbatas.',
  NATIONAL_BASELINE_UNVALIDATED: 'Analisis tim nasional masih memakai baseline riset yang belum tervalidasi.',
  NEUTRAL_VENUE_UNVERIFIED: 'Lokasi netral pertandingan belum dapat diverifikasi.',
  MODEL_MARKET_DISAGREEMENT: 'Proyeksi tim nasional terlalu jauh dari harga pasar; analisis ditahan.',
  MARKET_BENCHMARK_UNAVAILABLE: 'Odds 1X2 lengkap diperlukan untuk memeriksa baseline tim nasional.',
  DUPLICATE_FIXTURE: 'Pertandingan yang sama sudah dianalisis dari fixture lain.',
};

export function reasonLabel(code: string): string {
  return REASONS[code] ?? `Analisis tertahan: ${code.replaceAll('_', ' ').toLowerCase()}.`;
}

export function forecastPicks(match: DetailedMatch): ForecastPick[] {
  // Pre-migration scanner picks are genuine engine outputs. They can be shown
  // as legacy results; never recreate the removed generic-rating analyzer.
  return match.projections ?? match.qualified_picks ?? match.picks ?? [];
}

export function isValue(pick: ForecastPick): boolean {
  return pick.analysis_status === 'value_candidate' ||
    (pick.analysis_status === undefined && Number.isFinite(pick.ev) && pick.ev >= 0.01 &&
      Number.isFinite(pick.conservative_ev) && pick.conservative_ev >= 0 && pick.odds >= 1.6 && pick.odds <= 2.5);
}

export function matchKey(match: DetailedMatch): string {
  return String(match.info.match_id ?? `${match.info.league}|${match.info.home}|${match.info.away}|${match.info.start_ts}`);
}

export function pickLabel(pick: ForecastPick, match: DetailedMatch): string {
  if (pick.market === '1x2') return pick.side === 'home' || pick.pick === 'Home' ? String(match.info.home) : pick.side === 'away' || pick.pick === 'Away' ? String(match.info.away) : pick.pick === 'Draw' ? 'Seri' : pick.pick;
  if (pick.market === 'ah') return pick.pick.replace(/^AH Home/, String(match.info.home)).replace(/^AH Away/, String(match.info.away));
  return pick.pick;
}
