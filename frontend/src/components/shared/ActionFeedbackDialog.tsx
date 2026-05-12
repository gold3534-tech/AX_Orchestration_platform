import { useEffect, useId, useRef, type ReactNode } from 'react';

type ActionFeedbackTone = 'success' | 'danger' | 'confirm' | 'info';

type ActionFeedbackDialogProps = {
  open: boolean;
  tone?: ActionFeedbackTone;
  title: string;
  description?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm?: () => void;
  onCancel?: () => void;
};

const toneClassName: Record<ActionFeedbackTone, string> = {
  success: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  danger: 'border-rose-200 bg-rose-50 text-rose-900',
  confirm: 'border-cyan-200 bg-cyan-50 text-cyan-950',
  info: 'border-stone-200 bg-stone-50 text-stone-900',
};

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

export function ActionFeedbackDialog({
  open,
  tone = 'info',
  title,
  description,
  confirmLabel = '확인',
  cancelLabel,
  onConfirm,
  onCancel,
}: ActionFeedbackDialogProps) {
  const dialogId = useId();
  const titleId = `${dialogId}-title`;
  const descriptionId = description ? `${dialogId}-description` : undefined;
  const dialogRef = useRef<HTMLElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialogRef.current?.focus();

    return () => {
      previousFocusRef.current?.focus();
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    function handleDocumentKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onCancel?.();
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

    document.addEventListener('keydown', handleDocumentKeyDown);

    return () => {
      document.removeEventListener('keydown', handleDocumentKeyDown);
    };
  }, [onCancel, open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-stone-950/30 p-4" role="presentation">
      <section
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        tabIndex={-1}
        className={`w-full max-w-md rounded-2xl border p-5 shadow-2xl ${toneClassName[tone]}`}
      >
        <h2 id={titleId} className="text-lg font-semibold">
          {title}
        </h2>
        {description ? (
          <div id={descriptionId} className="mt-2 text-sm leading-6 opacity-90">
            {description}
          </div>
        ) : null}
        <div className="mt-5 flex justify-end gap-2">
          {cancelLabel ? (
            <button
              type="button"
              onClick={onCancel}
              className="rounded-full border border-stone-300 bg-white px-4 py-2 text-sm font-semibold text-stone-700 hover:bg-stone-50"
            >
              {cancelLabel}
            </button>
          ) : null}
          <button
            type="button"
            onClick={onConfirm ?? onCancel}
            className="rounded-full bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-300"
          >
            {confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}
