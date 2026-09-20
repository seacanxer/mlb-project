import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Prediksi Pertandingan — FC Market Intelligence',
  description: 'Jelajahi analisis 1X2, Asian Handicap, O/U dan BTTS per pertandingan dengan status data dan pilihan value yang jelas.',
};

export default function FcScheduleLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
