/**
 * components/fc/Schedule.tsx
 *
 * Today's Schedule list (brief FR-3): all 24h fixtures, has-pick badge with
 * link-back, plain-language coverage, countdown to nearest kickoff.
 */
'use client';
import Link from 'next/link';
import type { DetailedMatch } from '@/lib/fc/types';
import { NULL_GLYPH } from '@/lib/fc/format';
import { formatKickoffWIB, kickoffCountdown } from '@/lib/fc/kickoff';
import { CoverageBadge } from './shared';

function fixtureTitle(m: DetailedMatch): string {
  const info = m.info ?? {};
  const home = (info['home'] as string) ?? '';
  const away = (info['away'] as string) ?? '';
  if (home || away) return `${home || '?'} vs ${away || '?'}`;
  return '—';
}

export function ScheduleTable({ matches }: { matches: DetailedMatch[] }) {
  const ordered = [...matches].sort(
    (a, b) => Number(a.info?.['start_ts'] ?? 0) - Number(b.info?.['start_ts'] ?? 0),
  );
  const next = ordered.find((m) => Number(m.info?.['start_ts'] ?? 0) * 1000 > Date.now());
  return (
    <div>
      {next && (
        <p className="fc-next" role="status">
          Laga terdekat: <strong>{fixtureTitle(next)}</strong> · {kickoffCountdown(next.info?.['start_ts'] as number)}
        </p>
      )}
      <div className="fc-table-wrap">
        <table className="data-table" aria-label="Jadwal 24 jam">
          <thead>
            <tr><th>Kickoff WIB</th><th>Liga</th><th>Fixture</th><th>Cakupan</th><th>Pick</th></tr>
          </thead>
          <tbody>
            {ordered.map((m, i) => {
              const info = m.info ?? {};
              const hasPick = (m.qualified_picks?.length ?? 0) > 0 || (m.picks?.length ?? 0) > 0;
              const league = (info['league'] as string) ?? NULL_GLYPH;
              return (
                <tr key={`${info['match_id'] ?? i}-${info['start_ts']}`}>
                  <td className="mono-val" style={{ fontSize: '0.8rem' }}>
                    {formatKickoffWIB(info['start_ts'] as number)}
                    <div className="muted">{kickoffCountdown(info['start_ts'] as number)}</div>
                  </td>
                  <td style={{ fontSize: '0.8rem' }}>{league}</td>
                  <td style={{ fontWeight: 600 }}>{fixtureTitle(m)}</td>
                  <td><CoverageBadge coverage={info['coverage_status'] as string | undefined} /></td>
                  <td>
                    {hasPick ? (
                      <Link href="/fc" className="chip chip-fc-official">ada pick →</Link>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="fc-cards">
        {ordered.map((m, i) => {
          const info = m.info ?? {};
          const hasPick = (m.qualified_picks?.length ?? 0) > 0 || (m.picks?.length ?? 0) > 0;
          return (
            <article key={`c-${info['match_id'] ?? i}`} className="card fc-card">
              <h3 className="fc-card-match">{fixtureTitle(m)}</h3>
              <p className="muted fc-card-league">{(info['league'] as string) ?? NULL_GLYPH} · {formatKickoffWIB(info['start_ts'] as number)} · {kickoffCountdown(info['start_ts'] as number)}</p>
              <div className="fc-card-foot">
                <CoverageBadge coverage={info['coverage_status'] as string | undefined} />
                {hasPick ? <Link href="/fc" className="chip chip-fc-official">ada pick →</Link> : <span className="muted">—</span>}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
