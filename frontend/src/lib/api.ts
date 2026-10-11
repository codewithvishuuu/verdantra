// Typed client mirroring API.md §§1-6. Backend Pydantic models must match field-for-field.
export interface Experiment {
  title: string;
  steps: string[];
  materials: string[];
  safety_notes: string[];
  estimated_minutes: number;
}

export interface AIAnalysis {
  observed_features: string[];
  cautious_explanation: string;
  uncertainty: string[];
  experiment: Experiment;
  model_id: string;
  disclaimer: string;
  analyzed_at: string;
}

export interface AnalyzeResponse {
  temp_image_id: string;
  image_preview_url: string;
  analysis: AIAnalysis;
}

export interface JournalEntry {
  id: string;
  title: string;
  created_at: string;
  image_url: string;
  thumbnail_url: string;
  analysis: AIAnalysis | null;
  user_notes: string;
  experiment_done: boolean;
  experiment_result: string | null;
}

export interface JournalListItem {
  id: string;
  title: string;
  created_at: string;
  thumbnail_url: string;
  has_ai: boolean;
  experiment_done: boolean;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: Record<string, unknown> };
  request_id: string;
}

export class ApiError extends Error {
  code: string;
  requestId: string;
  status: number;
  details: Record<string, unknown>;
  constructor(status: number, body: ApiErrorBody) {
    super(body.error.message);
    this.status = status;
    this.code = body.error.code;
    this.requestId = body.request_id;
    this.details = body.error.details ?? {};
  }
}

async function handle(res: Response) {
  const requestId = res.headers.get('X-Request-Id') ?? 'unknown';
  if (res.ok) {
    if (res.status === 204) return null;
    return res.json();
  }
  let body: ApiErrorBody;
  try {
    body = await res.json();
  } catch {
    body = {
      error: { code: 'unknown', message: `Request failed (HTTP ${res.status}). Please retry.` },
      request_id: requestId,
    };
  }
  throw new ApiError(res.status, body);
}

export const api = {
  health(): Promise<{ status: string; db: string; ai: string; model_id: string; provider: string }> {
    return fetch('/healthz', { headers: { Accept: 'application/json' } }).then(handle);
  },
  analyze(image: File, notes_hint?: string): Promise<AnalyzeResponse> {
    const form = new FormData();
    form.append('image', image);
    if (notes_hint?.trim()) form.append('notes_hint', notes_hint.trim().slice(0, 280));
    return fetch('/api/v1/observations/analyze', { method: 'POST', body: form }).then(handle);
  },
  saveEntry(payload: {
    temp_image_id: string;
    ai_analysis: AIAnalysis | null;
    user_notes: string;
    experiment_done: boolean;
    experiment_result?: string;
  }): Promise<JournalEntry> {
    return fetch('/api/v1/journal-entries', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(handle);
  },
  list(): Promise<{ entries: JournalListItem[]; total: number }> {
    return fetch('/api/v1/journal-entries').then(handle);
  },
  detail(id: string): Promise<JournalEntry> {
    return fetch(`/api/v1/journal-entries/${encodeURIComponent(id)}`).then(handle);
  },
  remove(id: string): Promise<null> {
    return fetch(`/api/v1/journal-entries/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    }).then(handle);
  },
};

export const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

export function validateImageFile(file: File): string | null {
  if (!ACCEPTED_TYPES.includes(file.type)) return 'Please choose a JPEG, PNG, or WebP photo.';
  if (file.size > MAX_IMAGE_BYTES) return 'That photo is over 10 MB. Please choose a smaller one.';
  if (file.size === 0) return 'That file looks empty. Please try a different photo.';
  return null;
}
