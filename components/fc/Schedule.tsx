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

function MatchRow({ m, showLeague = false }: { m: DetailedMatch; showLeague?: boolean }) {
  const info = m.info ?? {};
  const pick = hasPick(m);
  return (
    <li className={`fc-match${pick ? ' fc-match-pick' : ''}`}>
      <span className="mono-val fc-match-time">
        {formatKickoffWIB(info['start_ts'] as number, 'HH:mm')}
      </span>
      <span className="fc-match-teams">
        <span className="fc-match-title">{fixtureTitle(m)}</span>
        <span className="muted fc-match-sub">
          {showLeague && typeof info['league'] === 'string' ? `${info['league']} · ` : ''}
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
}

type SortMode = 'league' | 'time';

export function ScheduleTable({ matches }: { matches: DetailedMatch[] }) {
  const groups = useMemo(() => groupByCountryLeague(matches), [matches]);
  // Track user toggles only. Default state:
  //   featured (Top 5 Europe) = expanded, other leagues = collapsed
  const [overrides, setOverrides] = useState<Set<string>>(new Set());
  const [sort, setSort] = useState<SortMode>('league');

  const flat = useMemo(
    () => [...matches].sort((a, b) => Number(a.info?.['start_ts'] ?? 0) - Number(b.info?.['start_ts'] ?? 0)),
    [matches],
  );
  const next = flat.find((m) => Number(m.info?.['start_ts'] ?? 0) * 1000 > Date.now());

  const toggle = (key: string) => {
    setOverrides((prev) => {
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
      <div className="fc-scanrow" role="group" aria-label="Urutkan jadwal">
        <button
          type="button"
          className={`btn btn-ghost btn-sm${sort === 'league' ? ' fc-sort-active' : ''}`}
          onClick={() => setSort('league')}
          aria-pressed={sort === 'league'}
        >
          🏆 Sort by Liga
        </button>
        <button
          type="button"
          className={`btn btn-ghost btn-sm${sort === 'time' ? ' fc-sort-active' : ''}`}
          onClick={() => setSort('time')}
          aria-pressed={sort === 'time'}
        >
          🕒 Sort by Time
        </button>
      </div>
      {sort === 'time' ? (
        <ul className="fc-matchlist fc-matchlist-flat" aria-label="Jadwal urut waktu">
          {flat.map((m, i) => (
            <MatchRow
              key={`${(m.info?.['match_id'] as string) ?? i}-${m.info?.['start_ts']}`}
              m={m}
              showLeague
            />
          ))}
        </ul>
      ) : (
      groups.map((country) => (
        <section key={country.country} aria-label={country.country} className="fc-country">
          <h2 className="fc-country-head">
            {country.featured ? '⭐ ' : ''}{country.country.toUpperCase()}
            <span className="muted"> · {country.total} match</span>
          </h2>
          {country.leagues.map((lg) => {
            const key = `${country.country}|${lg.league}`;
            const defaultOpen = country.featured === true;
            const open = overrides.has(key) ? !defaultOpen : defaultOpen;
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
                    {lg.matches.map((m, i) => (
                      <MatchRow
                        key={`${(m.info?.['match_id'] as string) ?? i}-${m.info?.['start_ts']}`}
                        m={m}
                      />
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </section>
      ))
      )}
    </div>
  );
}
