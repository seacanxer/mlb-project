/**
 * components/fc/Schedule.tsx
 *
 * Today's Schedule as a sportsbook-style match list: Country → League →
 * matches, with collapsible league subgroups ("display matches (N)").
 * One markup serves desktop + mobile (stacked rows, no separate table).
 */
'use client';
import { useMemo, useState } from 'react';
import Link from 'next/link';
import type { DetailedMatch } from '@/lib/fc/types';
import { NULL_GLYPH } from '@/lib/fc/format';
import { formatKickoffWIB, kickoffCountdown } from '@/lib/fc/kickoff';
import { groupByCountryLeague } from '@/lib/fc/grouping';
import { CoverageBadge } from './shared';

function fixtureTitle(m: DetailedMatch): string {
  const info = m.info ?? {};
  const home = (info['home'] as string) ?? '';
  const away = (info['away'] as string) ?? '';
  if (home || away) return `${home || '?'} vs ${away || '?'}`;
  return '—';
}

function hasPick(m: DetailedMatch): boolean {
  return (m.qualified_picks?.length ?? 0) > 0 || (m.picks?.length ?? 0) > 0;
}

export function ScheduleTable({ matches }: { matches: DetailedMatch[] }) {
  const groups = useMemo(() => groupByCountryLeague(matches), [matches]);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const flat = useMemo(
    () => [...matches].sort((a, b) => Number(a.info?.['start_ts'] ?? 0) - Number(b.info?.['start_ts'] ?? 0)),
    [matches],
  );
  const next = flat.find((m) => Number(m.info?.['start_ts'] ?? 0) * 1000 > Date.now());

  const toggle = (key: string) => {
    setCollapsed((prev) => {
      const nextSet = new Set(prev);
      if (nextSet.has(key)) nextSet.delete(key);
      else nextSet.add(key);
      return nextSet;
    });
  };

  return (
    <div>
      {next && (
        <p className="fc-next" role="status">
          Laga terdekat: <strong>{fixtureTitle(next)}</strong> · {kickoffCountdown(next.info?.['start_ts'] as number)}
        </p>
      )}
      {groups.map((country) => (
        <section key={country.country} aria-label={country.country} className="fc-country">
          <h2 className="fc-country-head">
            {country.country.toUpperCase()}
            <span className="muted"> · {country.total} match</span>
          </h2>
          {country.leagues.map((lg) => {
            const key = `${country.country}|${lg.league}`;
            const open = !collapsed.has(key);
            return (
              <div key={key} className="fc-league">
                <button
                  type="button"
                  className="fc-league-head"
                  aria-expanded={open}
                  onClick={() => toggle(key)}
                >
                  <span className="fc-league-name">{lg.league}</span>
                  <span className="muted">display matches ({lg.matches.length})</span>
                  <span aria-hidden="true">{open ? '▾' : '▸'}</span>
                </button>
                {open && (
                  <ul className="fc-matchlist">
                    {lg.matches.map((m, i) => {
                      const info = m.info ?? {};
                      const pick = hasPick(m);
                      return (
                        <li
                          key={`${info['match_id'] ?? i}-${info['start_ts']}`}
                          className={`fc-match${pick ? ' fc-match-pick' : ''}`}
                        >
                          <span className="mono-val fc-match-time">
                            {formatKickoffWIB(info['start_ts'] as number, 'HH:mm')}
                          </span>
                          <span className="fc-match-teams">
                            <span className="fc-match-title">{fixtureTitle(m)}</span>
                            <span className="muted fc-match-sub">
                              {formatKickoffWIB(info['start_ts'] as number)} · {kickoffCountdown(info['start_ts'] as number)}
                            </span>
                          </span>
                          <span className="fc-match-side">
                            <CoverageBadge coverage={info['coverage_status'] as string | undefined} />
                            {pick ? (
                              <Link href="/fc" className="chip chip-fc-official">ada pick →</Link>
                            ) : (
                              <span className="muted">{NULL_GLYPH}</span>
                            )}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            );
          })}
        </section>
      ))}
    </div>
  );
}
