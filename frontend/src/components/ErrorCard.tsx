import { ApiError } from '../lib/api';

/** Standard error card per DESIGN.md §5 + API.md §6: verbatim message, Retry, request_id. */
export function ErrorCard({
  err,
  onRetry,
  retryLabel = 'Retry',
}: {
  err: unknown;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  const message =
    err instanceof ApiError
      ? err.message
      : err instanceof Error
        ? err.message
        : 'Something went wrong. Please retry.';
  const requestId = err instanceof ApiError ? err.requestId : undefined;

  return (
    <div role="alert" className="enter rounded-card border border-line bg-card p-4">
      <p className="font-medium text-danger">Something needs your attention</p>
      <p className="mt-1 break-words text-sm">{message}</p>
      {requestId && (
        <p className="mt-2 font-mono text-xs text-muted">request_id: {requestId}</p>
      )}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 min-h-[44px] rounded-field bg-moss px-4 text-sm font-semibold text-white hover:bg-moss-dark"
        >
          {retryLabel}
        </button>
      )}
    </div>
  );
}
