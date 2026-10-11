import { useEffect, useState } from 'react';
import { ApiError, api, type AIAnalysis, type AnalyzeResponse } from '../lib/api';
import { UploadCard, type PickedImage } from '../components/UploadCard';
import { AIPanel, AIUnavailablePanel } from '../components/AIPanel';
import { ObservationForm } from '../components/ObservationForm';
import { ErrorCard } from '../components/ErrorCard';

/**
 * Flow 1 + Flow 2 (USER_FLOWS.md): photograph → analyze → record → save.
 * Draft (photo + notes) survives API errors within the session.
 */
export function NewObservation({ navigate }: { navigate: (to: string) => void }) {
  const [picked, setPicked] = useState<PickedImage | null>(null);
  const [hint, setHint] = useState('');
  const [analyzing, setAnalyzing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [fallbackTempId, setFallbackTempId] = useState<string | null>(null);
  const [aiFailed, setAiFailed] = useState<unknown>(null);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [elapsed, setElapsed] = useState(0);

  // Honest loading clock: measured client-side seconds, never a fake percentage.
  useEffect(() => {
    if (!analyzing) return;
    const startedAt = Date.now();
    const id = window.setInterval(
      () => setElapsed(Math.floor((Date.now() - startedAt) / 1000)),
      500,
    );
    return () => window.clearInterval(id);
  }, [analyzing]);

  const analyze = async () => {
    if (!picked || analyzing) return;
    setAnalyzing(true);
    setElapsed(0);
    setAiFailed(null);
    setFallbackTempId(null);
    try {
      const res = await api.analyze(picked.file, hint);
      setResult(res);
    } catch (e) {
      // Honest failure path only — never synthesize a result (API.md §6, AI_SYSTEM.md §5).
      // Preserve server temp_image_id from error details so retry/save need no re-upload.
      setResult(null);
      setAiFailed(e);
      const maybeId = e instanceof ApiError ? e.details?.temp_image_id : undefined;
      if (typeof maybeId === 'string' && maybeId.length > 0) setFallbackTempId(maybeId);
    } finally {
      setAnalyzing(false);
    }
  };

  const saveTempId = result?.temp_image_id ?? fallbackTempId;
  const canSaveWithoutAI = saveTempId != null;

  const save = async (v: { notes: string; done: boolean; result: string }) => {
    if (!picked || saving || !saveTempId) return;
    setSaving(true);
    setSaveError(null);
    try {
      // Save-without-AI is allowed when the helper is down (DESIGN.md §5),
      // but only with a real server-issued temp_image_id — never invented.
      const entry = await api.saveEntry({
        temp_image_id: saveTempId,
        ai_analysis: result?.analysis ?? null,
        user_notes: v.notes,
        experiment_done: v.done,
        experiment_result: v.result || undefined,
      });
      navigate(`/journal/${entry.id}`);
    } catch (e) {
      setSaveError(e);
    } finally {
      setSaving(false);
    }
  };

  // DESIGN.md §5 outage behavior covers every AI-down code (API.md §6 503/504 row).
  // ai_busy is included: the amber panel + retry fits a busy slot, and no
  // temp id exists yet so the save form correctly stays hidden.
  const aiGone = (e: unknown) =>
    e instanceof ApiError &&
    ['ai_unavailable', 'api_auth_error', 'api_quota_exhausted', 'ai_timeout', 'ai_bad_response', 'ai_busy'].includes(
      e.code,
    );

  const analyzeLabel = !analyzing
    ? result
      ? 'Analyze again'
      : 'Analyze visible features'
    : elapsed > 0
      ? `Analyzing… ${elapsed}s elapsed`
      : 'Analyzing…';

  return (
    <div className="space-y-4">
      <div>
        <p className="font-mono text-xs uppercase tracking-widest text-muted">Field book · No. 01</p>
        <h1 className="ledger-numeral mt-1 text-4xl">A slow look outdoors</h1>
        <p className="mt-2 max-w-prose text-sm text-muted">
          Photograph one thing outside. The model describes only what it can see and suggests a
          short experiment. Your notes are the record that counts.
        </p>
      </div>

      <UploadCard
        picked={picked}
        onPick={(img) => {
          setPicked(img);
          setResult(null);
          setAiFailed(null);
          setFallbackTempId(null);
        }}
        onClear={() => {
          setPicked(null);
          setResult(null);
          setAiFailed(null);
          setFallbackTempId(null);
        }}
        hint={hint}
        onHint={setHint}
        disabled={analyzing || saving}
      />

      <div>
        <button
          type="button"
          disabled={!picked || analyzing || saving}
          onClick={analyze}
          className="min-h-[44px] w-full rounded-field bg-moss px-4 text-sm font-semibold text-white hover:bg-moss-dark disabled:opacity-50 sm:w-auto"
        >
          {analyzeLabel}
        </button>
        {analyzing && (
          <div role="status" className="enter mt-3 rounded-card border border-line bg-card p-4">
            <p className="font-medium">Examining visible evidence…</p>
            <p className="mt-1 text-sm text-muted">
              This can take a minute or more. Nothing is saved yet.
            </p>
          </div>
        )}
      </div>

      {result && (
        <AIPanel key={result.temp_image_id} analysis={result.analysis satisfies AIAnalysis} />
      )}
      {aiFailed != null &&
        (aiGone(aiFailed) ? (
          <AIUnavailablePanel onRetry={analyze} />
        ) : (
          <ErrorCard err={aiFailed} onRetry={analyze} retryLabel="Try a different photo" />
        ))}

      {(result != null || (aiFailed != null && aiGone(aiFailed) && canSaveWithoutAI)) && (
        <ObservationForm saving={saving} onSave={save} />
      )}
      {saveError != null && <ErrorCard err={saveError} onRetry={() => setSaveError(null)} retryLabel="Dismiss" />}
    </div>
  );
}
