import type { HealthState } from '../App';

/**
 * Sticky header per DESIGN.md §5: logo lockup left, nav right, /healthz dot.
 * Logo slot uses the provided asset verbatim once supplied (see assets/logo/LOGO_README.md).
 * Health state is owned by App (single /healthz fetch shared with the footer).
 */
export function Header({
  route,
  navigate,
  health,
}: {
  route: string;
  navigate: (to: string) => void;
  health: HealthState | null;
}) {

  const dot = !health ? 'bg-line' : health.ai === 'ok' ? 'bg-moss' : 'bg-amber';
  const label = !health
    ? 'Service status unknown'
    : `Service ${health.status}; AI helper ${health.ai} (${health.model_id})`;

  const link = (to: string, text: string) => (
    <button
      key={to}
      type="button"
      onClick={() => navigate(to)}
      aria-current={route === to ? 'page' : undefined}
      className={`min-h-[44px] rounded-field px-3 text-sm font-medium transition-colors ${
        route === to ? 'bg-moss text-white' : 'text-ink hover:bg-fern'
      }`}
    >
      {text}
    </button>
  );

  return (
    <header className="sticky top-0 z-10 border-b border-line bg-paper/95 backdrop-blur">
      <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-x-3 gap-y-2 px-4 py-3">
        <button
          type="button"
          onClick={() => navigate('/')}
          className="flex min-h-[44px] items-center gap-2"
          aria-label="Verdantra home"
        >
          {/* Emblem crop of the provided logo (assets/verdantra-logo.png).
              Original artwork verbatim: no redraw, recolor, or distortion. */}
          <img
            src="/verdantra-emblem.png"
            alt="Verdantra emblem"
            className="h-8 w-auto"
          />
          <span className="font-display text-xl tracking-tight">Verdantra</span>
        </button>
        <nav aria-label="Primary" className="flex items-center gap-1">
          {link('/', 'New observation')}
          {link('/journal', 'Journal')}
          <span
            title={label}
            aria-label={label}
            role="status"
            className={`ml-2 h-2.5 w-2.5 rounded-full ${dot}`}
          />
        </nav>
      </div>
    </header>
  );
}
