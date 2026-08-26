'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const NAV_LINKS = [
  { href: '/',                  label: 'Daily Slate' },
  { href: '/results',           label: 'Results' },
  { href: '/analysis-data',     label: 'Analysis Data' },
  { href: '/data-health',       label: 'Data Health' },
  { href: '/forecast-history',  label: 'Forecast History' },
  { href: '/backtest',          label: 'Backtest' },
  { href: '/settings',          label: 'Settings' },
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
    </nav>
  );
}
