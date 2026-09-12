/**
 * components/fc/shared.tsx
 *
 * Shared FC primitives: status/tier badges, health banner, empty/error
 * states, skeleton, permanent disclaimer (brief FR-5).
 *
 * Visual honesty rules (brief §0.3, DoD):
 * - watch/shadow NEVER styled as equal to full/official (dimmed + separated).
 * - calibrated_prob null renders "—", never a number (enforced at call sites
 *   via formatCalibratedProb).
 */
'use client';
import Link from 'next/link';
import type { HealthResponse } from '@/lib/fc/types';
import { formatKickoffWIB } from '@/lib/fc/kickoff';

export const DISCLAIMER_TEXT =
  'Estimasi model, belum tervalidasi sepenuhnya, bukan jaminan profit. Bertanggung jawablah dalam bermain.';

export function Disclaimer({ compact = false }: { compact?: boolean }) {
  return (
    <p className="fc-disclaimer" role="note">
      ⚠️ {DISCLAIMER_TEXT}
      {!compact && (
        <>
          {' '}
          <Link href="/fc/schedule">Lihat jadwal &amp; cakupan data</Link>.
        </>
      )}
    </p>
  );
}

const MARKET_LABEL: Record<string, string> = { ah: 'AH', ou: 'O/U', btts: 'BTTS', '1x2': '1X2' };

export function MarketBadge({ market }: { market: string }) {
  return <span className="chip chip-fc-market">{MARKET_LABEL[market?.toLowerCase()] ?? market ?? '—'}</span>;
}

export function StatusBadge({ decision, isTop }: { decision: string; isTop?: boolean }) {
  if (isTop || decision === 'top_pick') return <span className="chip chip-fc-top">★ Top Pick</span>;
  if (decision === 'official') return <span className="chip chip-fc-official">Official</span>;
  return <span className="chip chip-fc-watch">Watch</span>;
}

/** Coverage in plain language (brief FR-3): never raw jargon. */
export function CoverageBadge({ coverage }: { coverage: string | undefined }) {
  if (coverage === 'full') return <span className="chip chip-fc-official">Rating lengkap</span>;
  if (coverage === 'shadow') return <span className="chip chip-fc-watch">Data terbatas</span>;
  if (coverage === 'market_only') return <span className="chip chip-fc-na">Jadwal saja</span>;
  return <span className="muted">—</span>;
}

export function EmptyState({ title, body, showWhy = false }: { title: string; body: string; showWhy?: boolean }) {
  return (
    <div className="fc-empty" role="status">
      <div className="fc-empty-icon" aria-hidden="true">📭</div>
      <p className="fc-empty-title">{title}</p>
      <p className="muted">{body}</p>
      {showWhy && (
        <p className="muted fc-empty-why">
          Volume pick rendah saat slate sepi adalah perilaku benar — gate menolak sinyal yang tidak lebih baik dari
          tebakan acak (anti-bias), bukan bug. Slot kosong tidak pernah diisi paksa.
        </p>
      )}
    </div>
  );
}

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="fc-error" role="alert">
      ⚠ {message}{' '}
      {onRetry && (
        <button className="btn btn-ghost btn-sm" onClick={onRetry}>
          Coba lagi
        </button>
      )}
    </div>
  );
}

export function SkeletonRows({ rows = 5, label = 'Loading…' }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} aria-live="polite">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="fc-skeleton" />
      ))}
    </div>
  );
}

/** Thin cross-page health line (brief FR-4). Never wipes existing data. */
export function HealthBanner({ health }: { health: HealthResponse | null }) {
  if (!health) return null;
  const d = (health.scan_state.diagnostics ?? {}) as Record<string, unknown>;
  const num = (v: unknown) => (typeof v === 'number' ? v : null);
  const full = num(d['full']);
  const shadow = num(d['shadow']);
  const blocked = num(d['blocked']);
  const counts = [full !== null && `${full} full`, shadow !== null && `${shadow} shadow`, blocked !== null && `${blocked} diblokir`]
    .filter(Boolean)
    .join(' · ');
  const last = health.scan_state.last_scan_time ? formatKickoffWIB(health.scan_state.last_scan_time) : 'belum pernah';
  if (health.engine_offline) {
    return (
      <div className="fc-health fc-health-off" role="status">
        ⚪ Engine offline — scan terakhir: {last}
        {counts ? ` · ${counts}` : ''} · menampilkan data terakhir yang tersedia.
      </div>
    );
  }
  return (
    <div className="fc-health" role="status">
      🟢 Scan terakhir: {last}
      {counts ? ` · ${counts}` : ''} · formula {health.formula_version}
    </div>
  );
}

export function ResultBadge({ result }: { result: string | null }) {
  if (result === 'W') return <span className="chip chip-fc-win">W</span>;
  if (result === 'L') return <span className="chip chip-fc-loss">L</span>;
  if (result === 'P') return <span className="chip chip-fc-push">P</span>;
  return <span className="muted">—</span>;
}
