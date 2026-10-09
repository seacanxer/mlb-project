import React from 'react';
import type { FixtureInfo, MatchAnalysis } from '@/lib/fc/types';
import { formatEv, formatOdds, formatProb } from '@/lib/fc/format';

type Secondary = NonNullable<MatchAnalysis['secondary_markets']>;
const GROUPS = [
  { title: 'Corner', rows: [['corner_1x2', 'Pemenang corner'], ['corner_hdp', 'Asian HDP'], ['corners_ou', 'O/U']] },
  { title: 'Kartu', rows: [['cards_1x2', 'Lebih banyak poin kartu'], ['cards_hdp', 'Asian HDP'], ['cards_ou', 'O/U'], ['red_card', 'Kartu merah'], ['team_cards_ou', 'O/U per tim']] },
];

export function SecondaryPredictionPanel({ secondary, info, market }: {
  secondary: Secondary; info: FixtureInfo; market: string;
}) {
  return <section className="prediction-secondary" aria-label="Prediksi corner dan kartu">
    <div className="prediction-secondary-heading"><strong>Prediksi corner & kartu</strong><span>Proyeksi model</span></div>
    <div className="prediction-count-groups">
      {GROUPS.filter((group) => market === 'all' || group.rows.some(([key]) => key === market)).map((group) => {
        const data = group.title === 'Corner' ? secondary.corners : secondary.cards;
        const home = group.title === 'Corner' ? secondary.corners?.home : secondary.cards?.home_points;
        const away = group.title === 'Corner' ? secondary.corners?.away : secondary.cards?.away_points;
        return <section className="prediction-count-group" key={group.title} aria-label={`Analisis ${group.title}`}>
          <h4>{group.title}</h4>
          {data ? <div className="prediction-count-summary">
            <strong>Projection {group.title === 'Corner' ? 'Corner' : 'poin kartu'}: {data.total.toFixed(2)}</strong>
            <span>{info.home || 'Home'} {home?.toFixed(2) ?? '—'} · {info.away || 'Away'} {away?.toFixed(2) ?? '—'}</span>
          </div> : <p className="prediction-secondary-unavailable">Histori {group.title.toLowerCase()} belum cukup untuk proyeksi.</p>}
          <dl className="prediction-count-results">
            {group.rows.filter(([key]) => market === 'all' || key === market).map(([key, label]) => {
              const projection = secondary.markets.find((row) => row.market === key);
              return <div className="prediction-count-row" key={key}>
                <dt>{label}</dt>
                <dd>{projection ? <>
                  <strong>{projection.pick}</strong>
                  <small>{projection.line != null ? `Line ${projection.line.toFixed(2)} · ` : ''}P(model) {formatProb(projection.probability)}</small>
                  <small>{projection.odds != null ? `@${formatOdds(projection.odds)} · EV ${formatEv(projection.ev)}` : 'Odds pasar belum tersedia'}</small>
                  {projection.line != null && <small>{projection.line_source === 'book' ? 'Line pasar' : 'Line proyeksi model'}</small>}
                </> : <span>Belum tersedia</span>}</dd>
              </div>;
            })}
          </dl>
          {group.title === 'Kartu' && <small className="prediction-secondary-note">Poin kartu: kuning = {secondary.cards?.yellow_points ?? 1}, merah = {secondary.cards?.red_points ?? 2}. Prediksi merah membutuhkan histori kartu merah.</small>}
        </section>;
      })}
    </div>
    <small className="prediction-secondary-note">Proyeksi belum berstatus Official. Odds hanya ditampilkan jika sumber dan satuan pasar cocok dengan model.
      {secondary.referee_status === 'unknown' ? ' Wasit belum terverifikasi; prediksi kartu masih terbatas.' : ''}</small>
  </section>;
}
