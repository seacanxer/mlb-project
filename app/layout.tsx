import type { Metadata } from 'next';
import './globals.css';
import { NavBar } from '@/components/NavBar';

export const metadata: Metadata = {
  title: 'MLB Analytics',
  description: 'Deterministic MLB Moneyline and Over/Under analysis. No AI, no guarantees — transparent formulas and honest abstention.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="page-wrapper">
          <NavBar />
          <main className="main-content">{children}</main>
        </div>
      </body>
    </html>
  );
}
