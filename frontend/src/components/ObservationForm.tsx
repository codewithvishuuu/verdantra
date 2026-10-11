import { useId, useState } from 'react';
import { UserBadge } from './Badges';

/**
 * User-observation form. Empty by default — AI text is never prefilled here.
 * Binds USER_FLOWS.md Flow 2 + API.md save rules (notes 1–2000 chars).
 */
export function ObservationForm({
  saving,
  onSave,
}: {
  saving: boolean;
  onSave: (v: { notes: string; done: boolean; result: string }) => void;
}) {
  const [notes, setNotes] = useState('');
  const [done, setDone] = useState(false);
  const [result, setResult] = useState('');
  const [tried, setTried] = useState(false);
  const notesId = useId();
  const resultId = useId();

  const notesError = tried && notes.trim().length === 0;

  return (
    <section
      aria-label="Your observation"
      className="rounded-card border border-line border-l-4 border-l-stub bg-clay p-4"
    >
      <UserBadge />
      <p className="mt-2 text-sm text-muted">What you did and saw. This is the record that counts.</p>

      <h2 className="mt-3 font-display text-lg">2 · Record what happened</h2>

      <label htmlFor={notesId} className="mt-2 block text-sm font-medium">
        Your notes <span aria-hidden="true">*</span>
      </label>
      <textarea
        id={notesId}
        value={notes}
        maxLength={2000}
        rows={4}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="What did you do, and what did you actually see?"
        aria-invalid={notesError}
        aria-describedby={notesError ? `${notesId}-error` : `${notesId}-count`}
        className="mt-1 w-full rounded-field border border-line bg-white p-3 text-sm"
      />
      <div className="mt-1 flex items-center justify-between text-xs">
        {notesError ? (
          <p id={`${notesId}-error`} role="alert" className="text-danger">
            Write at least a sentence about what you saw.
          </p>
        ) : (
          <span />
        )}
        <span id={`${notesId}-count`} className="text-muted">
          {notes.length}/2000
        </span>
      </div>

      <label className="mt-3 flex min-h-[44px] cursor-pointer items-center gap-2 text-sm font-medium">
        <input
          type="checkbox"
          checked={done}
          onChange={(e) => setDone(e.target.checked)}
          className="h-5 w-5 accent-moss"
        />
        I tried the suggested experiment
      </label>

      <label htmlFor={resultId} className="mt-2 block text-sm font-medium">
        What happened? <span className="font-normal text-muted">(optional)</span>
      </label>
      <textarea
        id={resultId}
        value={result}
        maxLength={2000}
        rows={3}
        onChange={(e) => setResult(e.target.value)}
        placeholder="e.g. the shaded leaf looked flatter…"
        className="mt-1 w-full rounded-field border border-line bg-white p-3 text-sm"
      />
      <p className="mt-1 text-right text-xs text-muted">{result.length}/2000</p>

      <button
        type="button"
        disabled={saving}
        onClick={() => {
          setTried(true);
          if (notes.trim().length === 0) return;
          onSave({ notes: notes.trim(), done, result: result.trim() });
        }}
        className="mt-2 min-h-[44px] w-full rounded-field bg-moss px-4 text-sm font-semibold text-white hover:bg-moss-dark disabled:opacity-50 sm:w-auto"
      >
        {saving ? 'Saving…' : 'Save to field journal'}
      </button>
    </section>
  );
}
