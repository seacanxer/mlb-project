/**
 * components/fc/ParlaySettlementBox.tsx
 *
 * Dedicated parlay settlement panel. Each manual slip gets its own refresh
 * button that force-settles that one parlay (ignoring the kickoff gate) via
 * POST /api/fc/settle?parlay_id=N, then polls GET until the job finishes.
 * The global button at the bottom settles every due slip at once.
 */
'use client';
import { useCallback, useState } from 'react';
import { fcGet, fcPost } from '@/lib/fc/client';
import type { ManualParlay } from '@/lib/fc/types';
import { formatOdds, formatProfit, NULL_GLYPH } from '@/lib/fc/format';
import { outcomeChipClass, slipStatusLabel } from '@/lib/fc/parlay';
import { MarketBadge } from './shared';

interface ParlaySettlementBoxProps {
  parlays: ManualParlay[];
  onSettled: () => void;
}

const POLL_MS = 3000;
const MAX_WAIT_MS = 240000;

function operatorToken(): string {
  try {
    return sessionStorage.getItem('fc-lock-operator-token') || '';
  } catch {
    return '';
  }
}

async function pollSettleJob(): Promise<{ status: string; message: string }> {
  let elapsed = 0;
  while (elapsed < MAX_WAIT_MS) {
    await new Promise((r) => setTimeout(r, POLL_MS));
    elapsed += POLL_MS;
    const status = await fcGet<{ running: boolean; last: { status: string; message?: string } | null }>('/api/fc/settle');
    if (!status.running && status.last) {
      return { status: status.last.status, message: status.last.message ?? 'Selesai.' };
    }
  }
  return { status: 'timeout', message: 'Settlement melebihi batas waktu.' };
}

export function ParlaySettlementBox({ parlays, onSettled }: ParlaySettlementBoxProps) {
  const [busyId, setBusyId] = useState<number | null>(null);
  const [busyAll, setBusyAll] = useState(false);
  const [note, setNote] = useState('');
  const [perSlip, setPerSlip] = useState<Record<number, string>>({});

  const runOne = useCallback(
    async (id: number) => {
      setBusyId(id);
      setPerSlip((m) => ({ ...m, [id]: 'Memeriksa skor tiap leg…' }));
      try {
        const token = operatorToken();
        await fcPost(
          `/api/fc/settle?parlay_id=${id}`,
          undefined,
          token ? { Authorization: `Bearer ${token}` } : {},
          20000,
        );
        const result = await pollSettleJob();
        setPerSlip((m) => ({ ...m, [id]: result.message }));
        if (result.status === 'done') onSettled();
      } catch (err) {
        setPerSlip((m) => ({ ...m, [id]: err instanceof Error ? err.message : 'Settlement gagal.' }));
      } finally {
        setBusyId(null);
      }
    },
    [onSettled],
  );

  const runAll = useCallback(async () => {
    setBusyAll(true);
    setNote('Mengambil skor final dan menyelesaikan pick/parlay…');
    try {
      const token = operatorToken();
      await fcPost('/api/fc/settle', undefined, token ? { Authorization: `Bearer ${token}` } : {}, 20000);
      const result = await pollSettleJob();
      setNote(result.message);
      onSettled();
    } catch (err) {
      setNote(err instanceof Error ? err.message : 'Settlement gagal.');
    } finally {
      setBusyAll(false);
    }
  }, [onSettled]);

  if (!parlays.length) return null;

  return (
    <div className="card" style={{ marginBottom: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
        <div>
          <h2 className="fc-section-title" style={{ marginBottom: '0.25rem' }}>Parlay settlement</h2>
          <p className="muted" style={{ fontSize: '0.82rem' }}>Refresh per slip memaksa cek skor tiap leg (abaikan gate kickoff)</p>
        </div>
        <button
          type="button"
          className="btn btn-ghost"
          disabled={busyAll || busyId !== null}
          aria-busy={busyAll}
          onClick={() => void runAll()}
        >
          {busyAll ? '↻ Settle semua…' : '↻ Settle semua slip'}
        </button>
      </div>

      {note && <p className="muted" role="status" style={{ fontSize: '0.82rem', marginTop: '0.5rem' }}>{note}</p>}

      <div style={{ marginTop: '0.75rem', display: 'grid', gap: '0.6rem' }}>
        {parlays.map((slip) => {
          const settled = slip.status !== 'pending';
          const chip = slipStatusLabel(slip.status);
          const cls = outcomeChipClass(slip.status === 'won' ? 'W' : slip.status === 'lost' ? 'L' : null);
          return (
            <div
              key={slip.id}
              className="card card-sm fc-parlay-row"
              style={{ padding: '0.7rem 0.9rem' }}
            >
              <span className="mono-val" style={{ fontWeight: 700 }}>#{slip.id}</span>
              <span className="chip" style={{ minWidth: '4.2rem', textAlign: 'center' }}>{chip}</span>
              <span className="mono-val muted" style={{ fontSize: '0.82rem' }}>
                {slip.legs ? `${slip.legs.length} leg · ` : ''}odds {formatOdds(slip.combined_odds)}
              </span>
              <span className="mono-val" style={{ fontSize: '0.85rem', fontWeight: 600 }}>
                {settled ? `profit ${formatProfit(slip.profit)}` : 'menunggu skor'}
              </span>
              {settled && slip.legs ? (
                <span className="muted" style={{ fontSize: '0.78rem' }}>
                  {slip.legs.filter((l) => l.result === 'won').length}W · {slip.legs.filter((l) => l.result === 'lost').length}L
                  {slip.legs.some((l) => l.result === 'push') ? ` · ${slip.legs.filter((l) => l.result === 'push').length}P` : ''}
                </span>
              ) : (
                <span className="muted" style={{ fontSize: '0.78rem' }}>
                  {slip.legs ? `${slip.legs.filter((l) => l.result === 'won').length}W · ${slip.legs.filter((l) => l.result === 'lost').length}L` : NULL_GLYPH}
                </span>
              )}
              <div className="fc-parlay-actions">
                {perSlip[slip.id] && <span className="muted" style={{ fontSize: '0.75rem' }}>{perSlip[slip.id]}</span>}
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  disabled={busyId !== null || busyAll || settled}
                  aria-busy={busyId === slip.id}
                  onClick={() => void runOne(slip.id)}
                  title={settled ? 'Slip sudah diselesaikan.' : 'Cek skor tiap leg parlay ini sekarang.'}
                >
                  {busyId === slip.id ? '↻…' : '↻ Refresh'}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
