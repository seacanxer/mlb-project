import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Result & ROI — FC Picks',
  description: 'Hasil settled, profit unit, ROI% flat-stake, hit rate, equity curve, dan breakdown per market serta kohort versi formula.',
};

export default function FcResultsLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
