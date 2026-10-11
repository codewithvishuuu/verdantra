import type { AIAnalysis } from '../lib/api';
import { AIBadge } from './Badges';

/**
 * Read-only AI panel. Binding copy/badges from DESIGN.md §4.
 * Never rendered inside the user-observation container and vice versa.
 */
export function AIPanel({ analysis }: { analysis: AIAnalysis }) {
  return (
    <section
      aria-label="AI prediction"
      className="enter break-words rounded-card border border-line border-l-4 border-l-moss bg-fern p-4"
    >
      <div className="flex flex-wrap items-center gap-2">
        <AIBadge />
      </div>
      <p className="mt-2 text-sm text-muted">
        What the model sees in this photo. May be wrong — confirm outdoors before trusting it.
      </p>
      <p className="mt-1 break-all font-mono text-xs text-muted">
        Model: {analysis.model_id} · {analysis.analyzed_at}
      </p>

      <h3 className="mt-3 font-display text-base">Visible evidence</h3>
      <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
        {analysis.observed_features.map((f) => (
          <li key={f}>{f}</li>
        ))}
      </ul>

      <p className="mt-3 text-sm leading-relaxed">{analysis.cautious_explanation}</p>

      <h3 className="mt-3 text-sm font-semibold text-amber">Uncertainty</h3>
      <ul className="mt-1 space-y-1 text-sm">
        {analysis.uncertainty.map((u) => (
          <li key={u}>⚠ {u}</li>
        ))}
      </ul>

      <div className="mt-4 rounded-field border border-line bg-card p-3">
        <p className="text-sm font-semibold">
          Try this · {analysis.experiment.title} (~{analysis.experiment.estimated_minutes} min)
        </p>
        <p className="mt-1 text-xs text-muted">
          Materials: {analysis.experiment.materials.join(', ')}
        </p>
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm">
          {analysis.experiment.steps.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ol>
        <div className="mt-2 rounded-field border border-amber/60 bg-paper p-2">
          <p className="text-xs font-bold uppercase tracking-wide text-amber">Safety</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs">
            {analysis.experiment.safety_notes.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
          <p className="mt-1 text-xs text-muted">
            Be safe outdoors. Never eat, touch, or approach anything because the AI suggested it.
          </p>
        </div>
      </div>

      <p className="mt-3 text-xs text-muted">{analysis.disclaimer}</p>
    </section>
  );
}

export function AIUnavailablePanel({ onRetry }: { onRetry: () => void }) {
  return (
    <section
      aria-label="AI unavailable"
      className="enter rounded-card border border-amber/60 bg-clay p-4"
    >
      <p className="font-medium">The AI helper is unavailable right now.</p>
      <p className="mt-1 text-sm">
        Your photo is kept — you can still write and save your own observation.
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-3 min-h-[44px] rounded-field bg-moss px-4 text-sm font-semibold text-white hover:bg-moss-dark"
      >
        Retry analysis
      </button>
    </section>
  );
}
