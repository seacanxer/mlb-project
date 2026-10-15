import type { DetailedMatch, ForecastPick, Market } from './types';
import { isActionable } from './quant';

export const FC_UI_VERSION = 'fc-market-board-v3';
export const PREDICTION_MARKETS: { key: Market; label: string }[] = [
  { key: '1x2', label: '1X2' }, { key: 'ah', label: 'Asian HDP' },
  { key: 'ou', label: 'O/U' }, { key: 'btts', label: 'BTTS' },
  { key: 'corners_ou', label: 'Corner O/U' }, { key: 'corner_hdp', label: 'Corner HDP' },
  { key: 'corner_1x2', label: 'Pemenang corner' }, { key: 'cards_1x2', label: 'Lebih banyak kartu' },
  { key: 'cards_hdp', label: 'Kartu HDP' },
  { key: 'cards_ou', label: 'Kartu O/U' }, { key: 'team_cards_ou', label: 'Kartu tim' }, { key: 'red_card', label: 'Kartu merah' },
];

const REASONS: Record<string, string> = {
  DIRECTION_ALTERNATIVE: 'Alternatif handicap pada tim lawan; berbeda dari arah utama 1X2.',
  LEAGUE_MODEL_UNAVAILABLE: 'Model untuk liga ini belum tersedia.',
  MODEL_UNAVAILABLE: 'Model liga belum berhasil dimuat.',
  TEAM_UNMATCHED: 'Identitas tim belum cocok dengan histori liga.',
  QUOTE_CAPTURE_FAILED: 'Odds pertandingan belum berhasil diverifikasi.',
  QUOTE_EXPIRED: 'Odds kedaluwarsa. Jalankan scan terbaru.',
  COMPLETE_MARKET_UNAVAILABLE: 'Pasangan odds pasar belum lengkap.',
  MODEL_NOT_VALIDATED: 'Model belum lolos validasi untuk Official.',
  RESCAN_REQUIRED: 'Jalankan scan untuk memperoleh analisis empat pasar.',
  STALE_TRAINING_DATA: 'Histori hasil terlalu lama; perbarui data liga.',
  ODDS_OUTSIDE_VALUE_RANGE: 'Odds di luar rentang value.',
  EV_BELOW_VALUE_THRESHOLD: 'EV belum mencapai ambang value.',
  REFERENCE_UNAVAILABLE: 'Harga referensi sharp (Pinnacle) belum tersedia; hanya forecast, bukan value pick.',
  QUANT_RESCAN_REQUIRED: 'Perbarui analisis untuk memperoleh metrik dan bukti harga terbaru.',
  REFERENCE_EVIDENCE_UNAVAILABLE: 'Bukti harga sharp belum tersedia atau sudah kedaluwarsa.',
  REFERENCE_CAPTURE_EXPIRED: 'Waktu pengambilan harga sharp sudah kedaluwarsa.',
  REFERENCE_SOURCE_EXPIRED: 'Harga sumber sharp sudah terlalu lama diperbarui.',
  REFERENCE_SOURCE_TIME_UNKNOWN: 'Waktu update sumber sharp tidak tersedia.',
  REFERENCE_CAPTURE_SKEW: 'Waktu pengambilan harga buku dan sharp terlalu berjauhan.',
  NO_POSITIVE_EV: 'Harga saat ini belum memberikan EV positif.',
  NO_VALUE_EDGE: 'Proyeksi tersedia untuk semua market, tetapi belum ada edge value ≥ 2% terhadap harga sharp.',
  MARKET_ONLY_NO_REFERENCE: 'Tanpa model dan tanpa referensi sharp: proyeksi dari harga 1xbit tanpa margin, bukan value pick.',
  REFERENCE_NO_EDGE: 'Dianalisis terhadap harga wajar Pinnacle (jalur referensi), tetapi odds 1xbit belum memberi edge ≥ 2%.',
  LEAGUE_MODEL_UNAVAILABLE_REFERENCE: 'Kompetisi tanpa model statistik; dinilai hanya terhadap referensi sharp.',
  REFERENCE_EDGE_IMPLAUSIBLE: 'Selisih harga dengan referensi sharp terlalu besar; kemungkinan odds basi atau salah cocok.',
  CONSERVATIVE_EV_BELOW_THRESHOLD: 'EV setelah penalti masih negatif.',
  TEAM_COVERAGE_MISSING: 'Histori tim belum cukup.',
  TEAM_LOW_COVERAGE: 'Sampel tim masih terbatas.',
  NATIONAL_BASELINE_UNVALIDATED: 'Analisis tim nasional masih memakai baseline riset yang belum tervalidasi.',
  NEUTRAL_VENUE_UNVERIFIED: 'Lokasi netral pertandingan belum dapat diverifikasi.',
  MODEL_MARKET_DISAGREEMENT: 'Probabilitas model terlalu jauh dari pasar; pilihan ditahan.',
  NO_QUALIFIED_FORECAST: 'Model tersedia, tetapi tidak ada pilihan yang lolos pemeriksaan kualitas.',
  MARKET_BENCHMARK_UNAVAILABLE: 'Odds 1X2 lengkap diperlukan untuk memeriksa baseline tim nasional.',
  DUPLICATE_FIXTURE: 'Pertandingan yang sama sudah dianalisis dari fixture lain.',
};

export function reasonLabel(code: string): string {
  return REASONS[code] ?? `Analisis tertahan: ${code.replaceAll('_', ' ').toLowerCase()}.`;
}

export function forecastPicks(match: DetailedMatch): ForecastPick[] {
  // Pre-migration scanner picks are genuine engine outputs. They can be shown
  // as legacy results; never recreate the removed generic-rating analyzer.
  return (match.projections ?? match.qualified_picks ?? match.picks ?? []).filter(isCardVisible);
}

export function isCardVisible(pick: ForecastPick): boolean {
  // Projections are no longer hidden for low prices; the confidence tier says how sure they are.
  return pick.market !== '1x2' || (pick.odds != null && Number.isFinite(pick.odds) && pick.odds > 1);
}

export const TIER_LABEL: Record<string, string> = {
  TINGGI: 'Confidence tinggi', SEDANG: 'Confidence sedang', RENDAH: 'Confidence rendah', SPEKULATIF: 'Spekulatif',
};

export function laneLabel(lane?: string): string {
  if (lane === 'reference_only') return 'Referensi Pinnacle';
  if (lane === 'market_only') return 'Harga pasar (tanpa model)';
  return 'Model liga';
}

export function isValue(pick: ForecastPick): boolean {
  return isActionable(pick);
}

export function matchKey(match: DetailedMatch): string {
  return String(match.info.match_id ?? `${match.info.league}|${match.info.home}|${match.info.away}|${match.info.start_ts}`);
}

export function pickLabel(pick: ForecastPick, match: DetailedMatch): string {
  if (pick.market === '1x2') return pick.side === 'home' || pick.pick === 'Home' ? String(match.info.home) : pick.side === 'away' || pick.pick === 'Away' ? String(match.info.away) : pick.pick === 'Draw' ? 'Seri' : pick.pick;
  if (pick.market === 'ah') return pick.pick.replace(/^AH Home/, String(match.info.home)).replace(/^AH Away/, String(match.info.away));
  return pick.pick;
}
