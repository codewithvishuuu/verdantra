import type { JournalListItem } from '../lib/api';
import { MiniBadge } from './Badges';

/**
 * Specimen-ticket card: perforated stub with oversized ledger numeral.
 * This is the differentiation anchor — recognizable with the logo removed.
 */
export function EntryCard({
  entry,
  index,
  onOpen,
}: {
  entry: JournalListItem;
  index: number;
  onOpen: () => void;
}) {
  const numeral = String(index + 1).padStart(2, '0');
  return (
    <article className="ticket enter flex overflow-hidden rounded-card border border-line bg-card transition-shadow hover:shadow-md">
      <div className="ticket-stub relative flex w-16 shrink-0 flex-col items-center justify-center bg-paper py-4">
        <span className="ledger-numeral text-2xl text-moss" aria-hidden="true">
          {numeral}
        </span>
        <span className="sr-only">Entry {numeral}</span>
        <span className="ticket-notch top-2" aria-hidden="true" />
        <span className="ticket-notch bottom-2" aria-hidden="true" />
      </div>
      <button
        type="button"
        onClick={onOpen}
        className="flex min-h-[88px] flex-1 items-center gap-3 p-3 text-left"
        aria-label={`Open ${entry.title}`}
      >
        <img
          src={entry.thumbnail_url}
          alt=""
          loading="lazy"
          className="h-16 w-16 shrink-0 rounded-field border border-line object-cover"
        />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-display text-base">{entry.title}</span>
          <span className="mt-0.5 block text-xs text-muted">
            {new Date(entry.created_at).toLocaleDateString()}
          </span>
          <span className="mt-1.5 flex flex-wrap gap-1">
            {entry.has_ai && <MiniBadge text="AI included" />}
            {entry.experiment_done && <MiniBadge text="Experiment done" />}
          </span>
        </span>
      </button>
    </article>
  );
}
