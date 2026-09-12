'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const NAV_LINKS = [
  { href: '/',                  label: 'Daily Slate' },
  { href: '/ai-picker',         label: '🤖 AI Picker' },
  { href: '/ai-final-picks',    label: '⭐ AI Final Picks' },
  { href: '/results',           label: 'Results' },
  { href: '/analysis-data',     label: 'Analysis Data' },
  { href: '/data-health',       label: 'Data Health' },
  { href: '/backtest',          label: 'Backtest' },
  { href: '/settings',          label: 'Settings' },
];

const FC_LINKS = [
  { href: '/fc',          label: "Today's Pick" },
  { href: '/fc/results',  label: 'Result & ROI' },
  { href: '/fc/schedule', label: 'Schedule' },
];

export function NavBar() {
  const pathname = usePathname();
  return (
    <nav className="nav" role="navigation" aria-label="Main navigation">
      <div className="nav-brand">
        <span aria-hidden="true">⚾</span>
        MLB Analytics
      </div>
      {NAV_LINKS.map((l) => (
        <Link
          key={l.href}
          href={l.href}
          className={`nav-link ${pathname === l.href || (l.href !== '/' && pathname.startsWith(l.href)) ? 'active' : ''}`}
          aria-current={pathname === l.href ? 'page' : undefined}
        >
          {l.label}
        </Link>
      ))}
      <span className="fc-nav-section" role="group" aria-label="FC picks">
        <span className="muted" style={{ fontSize: '0.75rem', alignSelf: 'center' }}>⚽ FC</span>
        {FC_LINKS.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className={`nav-link ${pathname === l.href || pathname.startsWith(l.href + '/') ? 'active' : ''}`}
          >
            {l.label}
          </Link>
        ))}
      </span>
    </nav>
  );
}
