import { beforeEach, describe, expect, it, vi } from 'vitest';
import { readGradeDetails } from '@/lib/fc/store';

const files = vi.hoisted(() => new Map<string, string>());
vi.mock('node:fs', () => ({ default: {
  readFileSync: (path: string) => files.get(path.split(/[/\\]/).pop()!) ?? '',
  existsSync: () => true,
} }));
beforeEach(() => files.clear());

describe('CSV model evaluation matches the temporal report', () => {
  it('keeps earliest forecast, excludes alternatives and late logging, and reads nested FT actuals', () => {
    const base = { home:'Home', away:'Away', match:'Home vs Away', market:'btts', source:'card', start_ts:1791500000 };
    const ledger = [
      { ...base, ledger_id:'first', match_id:'p1', probability:.55, first_seen_at:'2026-10-08T00:00:00Z' },
      { ...base, ledger_id:'later', match_id:'p2', probability:.9, first_seen_at:'2026-10-08T01:00:00Z' },
      { ...base, ledger_id:'late', first_seen_at:'2026-10-09T00:00:00Z' },
      { ...base, ledger_id:'option', market:'ou', source:'market_option' },
    ];
    const grades = ledger.map(e => ({ ledger_id:e.ledger_id, market:e.market, actual:{home_goals:2,away_goals:0}, outcome:'loss' }));
    files.set('projection_ledger.jsonl', ledger.map(x => JSON.stringify(x)).join('\n'));
    files.set('projection_grades.jsonl', [...grades, grades[0]].map(x => JSON.stringify(x)).join('\n'));
    const rows = readGradeDetails();
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ model_probability:.55, score:'2-0', home_goals:2, away_goals:0 });
  });
});
