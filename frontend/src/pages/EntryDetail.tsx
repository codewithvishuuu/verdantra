import { useEffect, useRef, useState } from 'react';
import { ApiError, api, type JournalEntry } from '../lib/api';
import { AIBadge, UserBadge } from '../components/Badges';
import { ErrorCard } from '../components/ErrorCard';

/** Flow 3b + Flow 4 (USER_FLOWS.md): detail with both panels + focus-trapped delete confirm. */
export function EntryDetail({
  id,
  navigate,
}: {
  id: string;
  navigate: (to: string) => void;
}) {
  const [entry, setEntry] = useState<JournalEntry | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const confirmRef = useRef<HTMLDivElement>(null);
  const deleteBtnRef = useRef<HTMLButtonElement>(null);

  const load = () => {
    setError(null);
    api
      .detail(id)
      .then(setEntry)
      .catch((e) => setError(e));
  };
  useEffect(load, [id]);

  // Focus trap: move focus into the dialog, return it on close (DESIGN.md §6).
  useEffect(() => {
    if (!confirming) return;
    confirmRef.current?.querySelector('button')?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setConfirming(false);
        deleteBtnRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [confirming]);

  const remove = async () => {
    setDeleting(true);
    try {
      await api.remove(id);
      navigate('/journal');
    } catch (e) {
      setError(e);
      setConfirming(false);
    } finally {
      setDeleting(false);
    }
  };

  if (error) {
    const gone = error instanceof ApiError && error.code === 'entry_not_found';
    return (
      <div className="space-y-4">
        <button
          type="button"
          onClick={() => navigate('/journal')}
          className="min-h-[44px] rounded-field border border-line px-4 text-sm font-medium hover:bg-card"
        >
          ← Back to journal
        </button>
        <ErrorCard
          err={gone ? new Error('This entry no longer exists.') : error}
          onRetry={gone ? undefined : load}
        />
      </div>
    );
  }
  if (!entry) {
    return (
      <div role="status" className="rounded-card border border-line bg-card p-4">
        <p className="text-sm text-muted">Pressing this specimen…</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <button
        type="button"
        onClick={() => navigate('/journal')}
        className="min-h-[44px] rounded-field border border-line px-4 text-sm font-medium hover:bg-card"
      >
        ← Back to journal
      </button>

      <div>
        <p className="font-mono text-xs uppercase tracking-widest text-muted">Specimen record</p>
        <h1 className="ledger-numeral mt-1 text-3xl">{entry.title}</h1>
        <p className="mt-1 break-all font-mono text-xs text-muted">
          {entry.id} · {entry.created_at}
        </p>
      </div>

      <img
        src={entry.image_url}
        alt={entry.title}
        className="w-full rounded-card border border-line object-contain"
      />

      <div className="grid gap-4 md:grid-cols-2">
        {entry.analysis ? (
          <section
            aria-label="AI prediction"
            className="break-words rounded-card border border-line border-l-4 border-l-moss bg-fern p-4"
          >
            <AIBadge />
            <p className="mt-2 text-sm text-muted">
              What the model sees in this photo. May be wrong — confirm outdoors before trusting
              it.
            </p>
            <p className="mt-1 break-all font-mono text-xs text-muted">
              Model: {entry.analysis.model_id} · {entry.analysis.analyzed_at}
            </p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
              {entry.analysis.observed_features.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
            <p className="mt-2 text-sm">{entry.analysis.cautious_explanation}</p>
          </section>
        ) : (
          <section aria-label="No AI prediction" className="rounded-card border border-line bg-card p-4">
            <p className="text-sm text-muted">Saved without an AI prediction.</p>
          </section>
        )}

        <section
          aria-label="Your observation"
          className="break-words rounded-card border border-line border-l-4 border-l-stub bg-clay p-4"
        >
          <UserBadge />
          <p className="mt-2 text-sm text-muted">What you did and saw. This is the record that counts.</p>
          <p className="mt-2 whitespace-pre-wrap text-sm">{entry.user_notes}</p>
          {entry.experiment_result && (
            <p className="mt-2 whitespace-pre-wrap text-sm">
              <span className="font-semibold">Experiment result: </span>
              {entry.experiment_result}
            </p>
          )}
          <p className="mt-2 text-xs text-muted">
            Experiment {entry.experiment_done ? 'done' : 'not marked as done'}
          </p>
        </section>
      </div>

      <div>
        <button
          ref={deleteBtnRef}
          type="button"
          onClick={() => setConfirming(true)}
          className="min-h-[44px] rounded-field border border-danger px-4 text-sm font-semibold text-danger hover:bg-danger hover:text-white"
        >
          Delete entry
        </button>
      </div>

      {confirming && (
        <div
          ref={confirmRef}
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="delete-title"
          aria-describedby="delete-desc"
          className="fixed inset-0 z-20 flex items-center justify-center bg-ink/40 p-4"
          onClick={() => {
            setConfirming(false);
            deleteBtnRef.current?.focus();
          }}
        >
          <div
            className="w-full max-w-sm rounded-card bg-card p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="delete-title" className="font-display text-xl">
              Delete this entry?
            </h2>
            <p id="delete-desc" className="mt-1 text-sm text-muted">
              This deletes the entry and its photo. This cannot be undone.
            </p>
            <div className="mt-4 flex gap-2">
              <button
                type="button"
                onClick={() => {
                  setConfirming(false);
                  deleteBtnRef.current?.focus();
                }}
                className="min-h-[44px] flex-1 rounded-field border border-line px-4 text-sm font-medium hover:bg-paper"
              >
                Keep it
              </button>
              <button
                type="button"
                disabled={deleting}
                onClick={remove}
                className="min-h-[44px] flex-1 rounded-field bg-danger px-4 text-sm font-semibold text-white disabled:opacity-50"
              >
                {deleting ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
