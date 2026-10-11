import { useCallback, useEffect, useState } from 'react';
import { Header } from './components/Header';
import { NewObservation } from './pages/NewObservation';
import { JournalList } from './pages/JournalList';
import { EntryDetail } from './pages/EntryDetail';
import { api } from './lib/api';

export interface HealthState {
  status: string;
  db: string;
  ai: string;
  model_id: string;
  provider: string;
}

function routeFromHash(): string {
  const h = window.location.hash.replace(/^#/, '') || '/';
  return h.startsWith('/') ? h : '/';
}

/** Local Ollama tags look like `gemma4:e2b`; hosted ids like `gemma-4-26b-a4b-it`.
 *  This prefix rule mirrors the documented model IDs — update it if they change. */
export function isLocalProvider(modelId: string): boolean {
  return modelId.startsWith('gemma4:');
}

/**
 * Hash router (no extra dependency — keeps the one-day budget).
 * Routes: `/` · `/journal` · `/journal/:id`. Unknown → friendly 404 card.
 */
export default function App() {
  const [route, setRoute] = useState(routeFromHash);
  const [health, setHealth] = useState<HealthState | null>(null);

  useEffect(() => {
    const onHash = () => setRoute(routeFromHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    let live = true;
    api
      .health()
      .then((h) => live && setHealth(h))
      .catch(() => live && setHealth(null));
    return () => {
      live = false;
    };
  }, [route]);

  const navigate = useCallback((to: string) => {
    window.location.hash = to;
  }, []);

  const detailMatch = route.match(/^\/journal\/([^/]+)$/);
  // Deployment mode drives the privacy disclosure. Unknown health keeps the
  // pre-existing Google wording (safe default: it over-discloses, never hides).
  const provider =
    health?.provider ?? (health && isLocalProvider(health.model_id) ? 'ollama' : 'gemini');

  return (
    <div className="paper-grain flex min-h-screen flex-col bg-paper font-sans text-ink">
      <Header route={detailMatch ? '/journal' : route} navigate={navigate} health={health} />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 pb-16 pt-6">
        {route === '/' && <NewObservation navigate={navigate} />}
        {route === '/journal' && <JournalList navigate={navigate} />}
        {detailMatch && <EntryDetail id={decodeURIComponent(detailMatch[1])} navigate={navigate} />}
        {route !== '/' && route !== '/journal' && !detailMatch && (
          <div className="rounded-card border border-line bg-card p-6 text-center">
            <p className="font-display text-2xl">That page wandered off-trail</p>
            <p className="mt-1 text-sm text-muted">The path you followed doesn’t exist.</p>
            <button
              type="button"
              onClick={() => navigate('/')}
              className="mt-4 min-h-[44px] rounded-field bg-moss px-4 text-sm font-semibold text-white hover:bg-moss-dark"
            >
              Back to a new observation
            </button>
          </div>
        )}
      </main>
      <footer className="mt-auto border-t border-line bg-paper">
        <div className="mx-auto max-w-3xl px-4 py-5 text-xs text-muted">
          {provider === 'ollama' ? (
            <p>
              On-device mode: analysis requests stay on the local Ollama service and are
              not sent to Google by this feature. Predictions are unverified · Be safe
              outdoors · No foraging or medical advice. Journal lives on this demo server.
            </p>
          ) : (
            <p>
              Photos you analyze are sent to Google's Gemini API (Free tier: content may be
              used to improve Google products, incl. human review — your own non-sensitive
              photos only) · Predictions are unverified · Be safe outdoors · No foraging or
              medical advice. Journal lives on this demo server.
            </p>
          )}
        </div>
      </footer>
    </div>
  );
}
