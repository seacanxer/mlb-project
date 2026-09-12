import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: "Today's Schedule — FC Picks",
  description: 'Semua fixture 24 jam ke depan (WIB): liga, countdown kickoff, status cakupan data, dan badge ada-pick.',
};

export default function FcScheduleLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
