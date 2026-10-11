import { useEffect, useState } from 'react';
import { api, type JournalListItem } from '../lib/api';
import { EntryCard } from '../components/EntryCard';
import { ErrorCard } from '../components/ErrorCard';

/** Flow 3a (USER_FLOWS.md): newest-first ticket ledger. */
export function JournalList({ navigate }: { navigate: (to: string) => void }) {
  const [entries, setEntries] = useState<JournalListItem[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = () => {
    setError(null);
    api
      .list()
      .then((r) => setEntries(r.entries))
      .catch((e) => setError(e));
  };

  useEffect(load, []);

  return (
    <div className="space-y-4">
      <div>
        <p className="font-mono text-xs uppercase tracking-widest text-muted">Field book · Ledger</p>
        <h1 className="ledger-numeral mt-1 text-4xl">Your journal</h1>
        {entries !== null && entries.length > 0 && (
          <p className="mt-1 text-sm text-muted">
            {entries.length === 1 ? '1 observation' : `${entries.length} observations`} · newest
            first
          </p>
        )}
      </div>

      {error != null && <ErrorCard err={error} onRetry={load} />}
      {entries === null && !error && (
        <div role="status" className="rounded-card border border-line bg-card p-4">
          <p className="text-sm text-muted">Opening your field book…</p>
        </div>
      )}
      {entries !== null && entries.length === 0 && (
        <div className="rounded-card border border-line bg-card p-6 text-center">
          <p aria-hidden="true" className="font-display text-4xl text-moss">
            ❧
          </p>
          <p className="mt-2 font-display text-xl">No entries yet</p>
          <p className="mt-1 text-sm text-muted">
            Your first slow look is one photo away.
          </p>
          <button
            type="button"
            onClick={() => navigate('/')}
            className="mt-4 min-h-[44px] rounded-field bg-moss px-4 text-sm font-semibold text-white hover:bg-moss-dark"
          >
            Make your first observation
          </button>
        </div>
      )}
      {entries !== null && entries.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {entries.map((e, i) => (
            <EntryCard key={e.id} entry={e} index={i} onOpen={() => navigate(`/journal/${e.id}`)} />
          ))}
        </div>
      )}
    </div>
  );
}
