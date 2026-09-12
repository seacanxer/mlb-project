import type { Metadata } from 'next';
import './fc.css';
import { HealthSlot } from '@/components/fc/HealthSlot';
import { Disclaimer } from '@/components/fc/shared';

export const metadata: Metadata = {
  title: 'FC Picks — Rekomendasi Betting Berbasis Data',
  description:
    'Rekomendasi pick AH, O/U, BTTS, 1X2 dari pipeline projection + gate anti-bias. ROI flat-stake jujur, tanpa pick fiktif.',
};

export default function FcLayout({ children }: { children: React.ReactNode }) {
  return (
    <div>
      <HealthSlot />
      {children}
      <footer>
        <Disclaimer />
      </footer>
    </div>
  );
}
