/**
 * components/FinalStateChip.tsx
 * Renders a typed final-state chip with color and text label.
 * State is communicated by text+icon, not color alone (WCAG 2.1 AA).
 */
import type { FinalState } from '@/lib/engine/types';

const STATE_CONFIG: Record<string, { cls: string; icon: string; label: string }> = {
  T1:               { cls: 'chip-t1',          icon: '★',  label: 'T1'          },
  T2:               { cls: 'chip-t2',          icon: '◆',  label: 'T2'          },
  SKIP:             { cls: 'chip-skip',         icon: '✕',  label: 'SKIP'        },
  NO_BET:           { cls: 'chip-nobet',        icon: '—',  label: 'NO BET'      },
  NEEDS_DATA:       { cls: 'chip-needs',        icon: '!',  label: 'NEEDS DATA'  },
  INVALIDATED:      { cls: 'chip-invalidated',  icon: '✕',  label: 'INVALIDATED' },
  OVER_LEAN:        { cls: 'chip-over',         icon: '↗',  label: 'OVER LEAN'   },
  OVER_STRONG_GAP:  { cls: 'chip-over',         icon: '↑↑', label: 'OVER'        },
  OVER_RISKY:       { cls: 'chip-over',         icon: '↑',  label: 'OVER RISKY'  },
  UNDER_LEAN:       { cls: 'chip-under',        icon: '↘',  label: 'UNDER LEAN'  },
  UNDER_STRONG_GAP: { cls: 'chip-under',        icon: '↓↓', label: 'UNDER'       },
  UNDER_RISKY:      { cls: 'chip-under',        icon: '↓',  label: 'UNDER RISKY' },
};

export function FinalStateChip({
  state,
  size = 'normal',
}: {
  state: string;
  size?: 'sm' | 'normal';
}) {
  const cfg = STATE_CONFIG[state] ?? { cls: 'chip-nobet', icon: '?', label: state };
  return (
    <span
      className={`chip ${cfg.cls}`}
      style={size === 'sm' ? { fontSize: '0.7rem', padding: '0.15rem 0.45rem' } : {}}
      aria-label={`Status: ${cfg.label}`}
      role="status"
    >
      <span aria-hidden="true">{cfg.icon}</span>
      {cfg.label}
    </span>
  );
}

export function ExperimentalBadge() {
  return (
    <span className="badge-experimental" title="O/U is experimental. Gap labels are not calibrated probabilities.">
      ⚗ Experimental
    </span>
  );
}
