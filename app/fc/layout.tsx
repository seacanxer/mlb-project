import type { Metadata } from 'next';
import './fc.css';
import { HealthSlot } from '@/components/fc/HealthSlot';
import { Disclaimer } from '@/components/fc/shared';
import { FC_UI_VERSION } from '@/lib/fc/predictions';

export const metadata: Metadata = {
  title: 'FC Picks — Rekomendasi Betting Berbasis Data',
  description:
    'Rekomendasi pick AH, O/U, BTTS, 1X2 dari pipeline projection + gate anti-bias. ROI flat-stake jujur, tanpa pick fiktif.',
};

export default function FcLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="fc-shell">
      <HealthSlot />
      {children}
      <footer>
        <Disclaimer />
        <p className="fc-build-label">FC Market Intelligence · UI {FC_UI_VERSION} · build {process.env.NEXT_PUBLIC_BUILD_COMMIT || 'unknown'}</p>
      </footer>
    </div>
  );
}
