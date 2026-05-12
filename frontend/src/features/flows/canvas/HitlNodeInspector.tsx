import { useEffect, useRef, useState } from 'react';
import type { FlowCanvasDraft } from '../hooks';

const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

function getFocusableElements(container: HTMLElement) {
  return Array.from(container.querySelectorAll<HTMLElement>(focusableSelector)).filter(
    (element) => !element.hasAttribute('disabled') && element.getAttribute('aria-hidden') !== 'true',
  );
}

function normalizeMaxAttempts(value: string) {
  const parsed = Number.parseInt(value, 10);

  if (!Number.isFinite(parsed) || parsed < 1) {
    return 3;
  }

  return Math.floor(parsed);
}

export function HitlNodeInspector({
  draft,
  hitlNode,
  onChangeDraft,
  onClose,
}: {
  draft: FlowCanvasDraft;
  hitlNode: FlowCanvasDraft['nodes'][number];
  onChangeDraft: (draft: FlowCanvasDraft) => void;
  onClose: () => void;
}) {
  const [maxAttempts, setMaxAttempts] = useState(
    typeof hitlNode.data.maxAttempts === 'number' ? String(hitlNode.data.maxAttempts) : '3',
  );
  const [prompt, setPrompt] = useState<string>(typeof hitlNode.data.prompt === 'string' ? hitlNode.data.prompt : '');
  const [onNeedsRevision, setOnNeedsRevision] = useState<string>(
    typeof hitlNode.data.onNeedsRevision === 'string' ? hitlNode.data.onNeedsRevision : 'retry_previous',
  );
  const [feedbackPropagation, setFeedbackPropagation] = useState<string>(
    typeof hitlNode.data.feedbackPropagation === 'string' ? hitlNode.data.feedbackPropagation : 'needs_revision_only',
  );
  const dialogRef = useRef<HTMLElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const titleId = `hitl-config-title-${hitlNode.id.replace(/[^a-zA-Z0-9_-]/g, '-')}`;

  useEffect(() => {
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialogRef.current?.focus();

    return () => {
      if (previousFocusRef.current?.isConnected) {
        previousFocusRef.current.focus();
      }
    };
  }, []);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onClose();
        return;
      }

      if (event.key !== 'Tab') {
        return;
      }

      const dialog = dialogRef.current;

      if (!dialog) {
        return;
      }

      const focusableElements = getFocusableElements(dialog);

      if (focusableElements.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }

      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];
      const activeElement = document.activeElement;
      const isDialogFocused = activeElement === dialog;

      if (event.shiftKey) {
        if (isDialogFocused || activeElement === firstElement || !dialog.contains(activeElement)) {
          event.preventDefault();
          lastElement.focus();
        }
        return;
      }

      if (isDialogFocused || activeElement === lastElement || !dialog.contains(activeElement)) {
        event.preventDefault();
        firstElement.focus();
      }
    }

    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [onClose]);

  function saveHitl() {
    const normalizedMaxAttempts = normalizeMaxAttempts(maxAttempts);
    onChangeDraft({
      ...draft,
      nodes: draft.nodes.map((node) =>
        node.id === hitlNode.id
          ? {
              ...node,
              data: {
                ...node.data,
                prompt: prompt,
                allowedDecisions: Array.isArray(node.data?.allowedDecisions)
                  ? node.data.allowedDecisions
                  : ['approved', 'needs_revision', 'rejected'],
                onNeedsRevision: onNeedsRevision,
                feedbackPropagation: feedbackPropagation,
                maxAttempts: normalizedMaxAttempts,
                metadata: node.data?.metadata ?? {},
              },
            }
          : node,
      ),
    });
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-stone-950/30 p-4">
      <section
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="w-full max-w-xl rounded-md border-2 border-[#7a5739] bg-[#fff6df] p-5 shadow-[6px_6px_0_#7a5739]"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-rose-700">HITL review</p>
            <h3 id={titleId} className="mt-1 text-base font-semibold text-stone-950">
              Configure HITL
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="pixel-button border-[#7a5739] bg-[#fffaf0] px-3 py-1 text-xs font-bold text-[#22170f] hover:bg-[#ffe6b3]"
          >
            Close
          </button>
        </div>

        <div className="mt-4 grid gap-4">
          <label className="grid gap-1">
            <span className="text-xs font-semibold text-stone-700">Review prompt</span>
            <textarea
              aria-label="Review prompt"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              className="min-h-[88px] rounded-xl border border-stone-300 bg-white px-3 py-2 text-sm font-medium text-stone-900"
            />
          </label>

          <label className="grid gap-1">
            <span className="text-xs font-semibold text-stone-700">Max retry attempts</span>
            <input
              aria-label="Max attempts"
              type="number"
              min={1}
              step={1}
              value={maxAttempts}
              onChange={(event) => setMaxAttempts(event.target.value)}
              className="rounded-xl border border-stone-300 bg-white px-3 py-2 text-sm font-medium text-stone-900"
            />
          </label>

          <label className="grid gap-1">
            <span className="text-xs font-semibold text-stone-700">Needs revision behavior</span>
            <select
              aria-label="Needs revision behavior"
              value={onNeedsRevision}
              onChange={(e) => setOnNeedsRevision(e.target.value)}
              className="rounded-xl border border-stone-300 bg-white px-3 py-2 text-sm font-medium text-stone-900"
            >
              <option value="retry_previous">Retry previous</option>
              <option value="continue_with_feedback">Continue with feedback</option>
            </select>
          </label>

          <label className="grid gap-1">
            <span className="text-xs font-semibold text-stone-700">Feedback propagation</span>
            <select
              aria-label="Feedback propagation"
              value={feedbackPropagation}
              onChange={(e) => setFeedbackPropagation(e.target.value)}
              className="rounded-xl border border-stone-300 bg-white px-3 py-2 text-sm font-medium text-stone-900"
            >
              <option value="needs_revision_only">Needs revision only</option>
              <option value="approved_and_needs_revision">Approved and needs revision</option>
            </select>
          </label>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="pixel-button border-[#7a5739] bg-[#fffaf0] px-4 py-2 text-sm font-bold text-[#22170f] hover:bg-[#ffe6b3]"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={saveHitl}
            className="pixel-button bg-rose-500 px-4 py-2 text-sm font-bold text-white hover:bg-rose-400"
          >
            Save HITL
          </button>
        </div>
      </section>
    </div>
  );
}
