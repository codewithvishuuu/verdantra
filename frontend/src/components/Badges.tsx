/** Binding badge copy from DESIGN.md §4 — do not reword without updating docs. */
export function AIBadge() {
  return (
    <span className="stamp inline-block rounded-full bg-moss px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-white">
      AI prediction — unverified
    </span>
  );
}

export function UserBadge() {
  return (
    <span className="stamp inline-block rounded-full bg-ink px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-white">
      Your observation — confirmed by you
    </span>
  );
}

export function MiniBadge({ text }: { text: string }) {
  return (
    <span className="inline-block rounded-full border border-line bg-paper px-2 py-0.5 text-xs font-medium text-muted">
      {text}
    </span>
  );
}
