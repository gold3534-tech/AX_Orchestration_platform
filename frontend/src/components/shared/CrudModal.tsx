import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from 'react';

type CrudModalProps = {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  role?: 'dialog' | 'alertdialog';
  descriptionId?: string;
  maxWidthClassName?: string;
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

function trapTabFocus(event: KeyboardEvent<HTMLElement>, container: HTMLElement) {
  if (event.key !== 'Tab') {
    return;
  }

  const focusableElements = getFocusableElements(container);

  if (focusableElements.length === 0) {
    event.preventDefault();
    container.focus();
    return;
  }

  const firstElement = focusableElements[0];
  const lastElement = focusableElements[focusableElements.length - 1];
  const activeElement = document.activeElement;
  const isContainerFocused = activeElement === container;

  if (event.shiftKey) {
    if (isContainerFocused || activeElement === firstElement || !container.contains(activeElement)) {
      event.preventDefault();
      lastElement.focus();
    }
    return;
  }

  if (isContainerFocused || activeElement === lastElement || !container.contains(activeElement)) {
    event.preventDefault();
    firstElement.focus();
  }
}

export function CrudModal({
  open,
  title,
  onClose,
  children,
  role = 'dialog',
  descriptionId,
  maxWidthClassName = 'max-w-2xl',
}: CrudModalProps) {
  const dialogId = useId();
  const titleId = `${dialogId}-title`;
  const dialogRef = useRef<HTMLDivElement>(null);
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

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      event.stopPropagation();
      onClose();
      return;
    }

    if (dialogRef.current) {
      trapTabFocus(event, dialogRef.current);
    }
  }

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#22170f]/50 p-4 backdrop-blur-sm">
      <div
        ref={dialogRef}
        role={role}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
        className={`flex max-h-[calc(100vh-2rem)] w-full flex-col rounded-md border-2 border-[#7a5739] bg-[#fff6df] text-stone-800 shadow-[8px_8px_0_#7a5739] ${maxWidthClassName}`}
      >
        <div className="flex items-center justify-between border-b-2 border-[#7a5739] bg-[#f8e8c8] px-5 py-4">
          <h2 id={titleId} className="text-lg font-black text-[#22170f]">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="pixel-button border-[#7a5739] bg-[#fffaf0] px-3 py-1 text-sm font-bold text-[#22170f] hover:bg-[#ffe6b3]"
          >
            Close
          </button>
        </div>
        <div className="overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
}
