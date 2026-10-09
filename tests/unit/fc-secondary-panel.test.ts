import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SecondaryPredictionPanel } from '@/components/fc/SecondaryPredictionPanel';
import type { MatchAnalysis } from '@/lib/fc/types';

type Secondary = NonNullable<MatchAnalysis['secondary_markets']>;
const secondary: Secondary = {
  availability: 'B', corners: { home: 4.5, away: 5.2, total: 9.7, n_eff: 8, dispersion: 3 },
  cards: { home: 1.7, away: 2, home_points: 1.9, away_points: 2.3, total: 4.2, n_eff: 8, dispersion: 3, referee_status: 'unknown' },
  markets: [
    { market: 'corner_1x2', pick: 'QPR', side: 'away', line: null, probability: .53, odds: null },
    { market: 'corner_hdp', pick: 'QPR +2.25', side: 'away', line: 2.25, probability: .6, odds: 1.92, line_source: 'book', ev: .04 },
    { market: 'cards_1x2', pick: 'QPR', side: 'away', line: null, probability: .51, odds: null },
    { market: 'cards_hdp', pick: 'QPR -0.25', side: 'away', line: -.25, probability: .5, odds: null, line_source: 'model-central' },
    { market: 'red_card', pick: 'Merah Tidak', side: 'no', line: null, probability: .8, odds: null },
  ].map((row) => ({ ...row, availability: 'B', status: 'projection', label: 'Proyeksi', p_market_novig: null, edge: null })) as Secondary['markets'],
};
const render = (data: Secondary, market = 'all') => renderToStaticMarkup(React.createElement(
  SecondaryPredictionPanel, { secondary: data, info: { home: 'West Ham', away: 'QPR' }, market }));

describe('secondary prediction card', () => {
  it('renders winner, handicap and red projection with honest quote provenance', () => {
    const html = render(secondary);
    for (const text of ['Pemenang corner', 'Lebih banyak poin kartu', 'Projection Corner: 9.70',
      'QPR +2.25', 'QPR -0.25', 'Merah Tidak', '1.92', 'Line pasar', 'Line proyeksi model', 'Odds pasar belum tersedia']) {
      expect(html).toContain(text);
    }
  });
  it('shows unavailable per lane and honors market filters', () => {
    expect(render({ availability: 'C', markets: [] })).toContain('Histori corner belum cukup');
    const html = render(secondary, 'cards_hdp');
    expect(html).toContain('QPR -0.25');
    expect(html).not.toContain('Pemenang corner');
    expect(html).not.toContain('Merah Tidak');
  });
});
