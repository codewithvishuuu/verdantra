import { useId, useRef, useState } from 'react';
import { validateImageFile } from '../lib/api';

export interface PickedImage {
  file: File;
  previewUrl: string;
}

/**
 * Upload card with viewfinder corner ticks (differentiation anchor detail).
 * Client pre-validation only; server re-validates per SECURITY.md §3.
 */
export function UploadCard({
  picked,
  onPick,
  onClear,
  hint,
  onHint,
  disabled,
}: {
  picked: PickedImage | null;
  onPick: (img: PickedImage) => void;
  onClear: () => void;
  hint: string;
  onHint: (v: string) => void;
  disabled: boolean;
}) {
  const [error, setError] = useState<string | null>(null);
  const inputId = useId();
  const hintId = useId();
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = (file: File | undefined) => {
    if (!file) return;
    const problem = validateImageFile(file);
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    onPick({ file, previewUrl: URL.createObjectURL(file) });
  };

  return (
    <section aria-labelledby={`${inputId}-label`} className="rounded-card border border-line bg-card p-4">
      <h2 id={`${inputId}-label`} className="font-display text-lg">
        1 · Photograph the outdoors
      </h2>
      <p className="mt-1 text-sm text-muted">
        A leaf, bark, rock, puddle, or sky — anything outdoors and safe to observe.
      </p>

      <div className="mt-3 grid gap-4 md:grid-cols-2">
        <div>
          <div
            className="viewfinder h-full rounded-card border-2 border-dashed border-line bg-parchment p-6 text-center"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          handleFile(e.dataTransfer.files?.[0]);
        }}
      >
        {!picked ? (
          <>
            <p className="font-medium">Drag a photo here, or</p>
            <button
              type="button"
              disabled={disabled}
              onClick={() => inputRef.current?.click()}
              className="mt-2 min-h-[44px] rounded-field bg-moss px-4 text-sm font-semibold text-white hover:bg-moss-dark disabled:opacity-50"
            >
              Choose photo / Take photo
            </button>
          </>
        ) : (
          <div className="flex flex-col items-center gap-2">
            <img
              src={picked.previewUrl}
              alt="Preview of your outdoor photo"
              className="max-h-64 rounded-field border border-line object-contain"
            />
            <p className="max-w-full break-all text-sm text-muted">
              {picked.file.name} · {(picked.file.size / 1024 / 1024).toFixed(1)} MB
            </p>
            <button
              type="button"
              onClick={onClear}
              className="min-h-[44px] rounded-field border border-line px-4 text-sm font-medium hover:bg-paper"
            >
              Use a different photo
            </button>
          </div>
        )}
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          capture="environment"
          className="sr-only"
          disabled={disabled}
          onChange={(e) => handleFile(e.target.files?.[0])}
          aria-describedby={error ? `${inputId}-error` : undefined}
        />
          </div>
          {error && (
            <p id={`${inputId}-error`} role="alert" className="mt-2 text-sm text-danger">
              {error}
            </p>
          )}
        </div>

        <div>
          <label htmlFor={hintId} className="text-sm font-medium">
            Habitat &amp; context <span className="font-normal text-muted">(optional)</span>
          </label>
          <p className="mt-1 text-xs text-muted">
            Where did you find it? Don’t include names or addresses.
          </p>
          <input
            id={hintId}
            value={hint}
            maxLength={280}
            disabled={disabled}
            onChange={(e) => onHint(e.target.value)}
            placeholder="e.g. on the park path after rain"
            className="mt-2 min-h-[44px] w-full rounded-field border border-line bg-white px-3 text-sm"
          />
          <p className="mt-1 text-right text-xs text-muted">{hint.length}/280</p>
        </div>
      </div>
    </section>
  );
}
