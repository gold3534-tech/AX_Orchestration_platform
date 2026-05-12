import { type KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react';

type DiagnosticSection = 'validate' | 'compatibility' | 'tools' | 'diagnostics';

type FlowTestConsoleProps = {
  open: boolean;
  flowAssetId: string;
  flowName: string;
  onClose: () => void;
  onValidateGraph: () => Promise<unknown>;
  onCompatibilityTest: () => Promise<unknown>;
  onToolMockCallCheck: () => Promise<unknown>;
  isBusy?: boolean;
};

const initialResults: Record<DiagnosticSection, unknown> = {
  validate: null,
  compatibility: null,
  tools: null,
  diagnostics: null,
};

const focusableSelector = [
  'button:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'a[href]',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

function getFocusableElements(container: HTMLElement) {
  return Array.from(container.querySelectorAll<HTMLElement>(focusableSelector)).filter(
    (element) => !element.hasAttribute('disabled') && element.getAttribute('aria-hidden') !== 'true',
  );
}

function stringifyDiagnostic(value: unknown) {
  return JSON.stringify(
    value ?? {},
    (_key, nestedValue) => {
      if (
        typeof nestedValue === 'string' &&
        nestedValue.length > 240 &&
        /base64|data:image/i.test(nestedValue.slice(0, 80))
      ) {
        return `${nestedValue.slice(0, 80)}<truncated:${nestedValue.length}>`;
      }
      return nestedValue;
    },
    2,
  );
}

function statusLabel(value: unknown) {
  if (value && typeof value === 'object' && 'status' in value) {
    const status = (value as { status?: unknown }).status;
    return typeof status === 'string' ? status : 'ready';
  }
  return value ? 'ready' : 'not run';
}

function resultSummary(value: unknown) {
  if (!value || typeof value !== 'object') return 'No result yet.';
  const record = value as Record<string, unknown>;
  if (record.mode === 'compatibility') {
    return record.provider_calls === 'blocked' ? 'Provider calls blocked.' : 'Compatibility diagnostics completed.';
  }
  if (record.mode === 'tool_mock_call') {
    const tools = Array.isArray(record.tools) ? record.tools.length : 0;
    return `${tools} tool checks recorded.`;
  }
  return 'Diagnostic result is available.';
}

export function FlowTestConsole({
  open,
  flowAssetId,
  flowName,
  onClose,
  onValidateGraph,
  onCompatibilityTest,
  onToolMockCallCheck,
  isBusy = false,
}: FlowTestConsoleProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const [activeSection, setActiveSection] = useState<DiagnosticSection>('validate');
  const [results, setResults] = useState<Record<DiagnosticSection, unknown>>(initialResults);
  const [error, setError] = useState<string | null>(null);

  const combinedDiagnostics = useMemo(
    () => ({
      validate: results.validate,
      compatibility: results.compatibility,
      tools: results.tools,
    }),
    [results.compatibility, results.tools, results.validate],
  );

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    setActiveSection('validate');
    setResults(initialResults);
    setError(null);
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialogRef.current?.focus();

    return () => {
      previousFocusRef.current?.focus();
    };
  }, [flowAssetId, open]);

  if (!open) return null;

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      event.stopPropagation();
      onClose();
      return;
    }

    if (event.key !== 'Tab' || !dialogRef.current) {
      return;
    }

    const focusableElements = getFocusableElements(dialogRef.current);
    if (focusableElements.length === 0) {
      event.preventDefault();
      dialogRef.current.focus();
      return;
    }

    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];
    const activeElement = document.activeElement;
    const isDialogFocused = activeElement === dialogRef.current;

    if (event.shiftKey) {
      if (isDialogFocused || activeElement === firstElement || !dialogRef.current.contains(activeElement)) {
        event.preventDefault();
        lastElement.focus();
      }
      return;
    }

    if (isDialogFocused || activeElement === lastElement || !dialogRef.current.contains(activeElement)) {
      event.preventDefault();
      firstElement.focus();
    }
  }

  async function run(section: DiagnosticSection, action: () => Promise<unknown>) {
    setError(null);
    setActiveSection(section);
    try {
      const result = await action();
      setResults((current) => ({ ...current, [section]: result, diagnostics: { ...current, [section]: result } }));
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'Diagnostic failed';
      setError(message);
      setResults((current) => ({ ...current, [section]: { status: 'failed', error: message } }));
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#22170f]/50 px-4 py-6">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="flow-test-console-title"
        tabIndex={-1}
        onKeyDown={handleKeyDown}
        className="grid max-h-[90vh] w-full max-w-6xl grid-cols-1 overflow-hidden rounded-md border-2 border-[#7a5739] bg-[#fff6df] shadow-[8px_8px_0_#7a5739] md:grid-cols-[minmax(0,1fr)_280px]"
      >
        <section className="overflow-auto p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 id="flow-test-console-title" className="mt-1 text-xl font-black text-[#22170f]">
                Flow Test Console: {flowName}
              </h2>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="pixel-button border-[#7a5739] bg-[#fffaf0] px-3 py-2 text-sm font-bold text-[#22170f] hover:bg-[#ffe6b3]"
            >
              Close
            </button>
          </div>
          {error ? <p className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}
          {(['validate', 'compatibility', 'tools'] as DiagnosticSection[]).map((section) => (
            <article key={section} className="mt-4 rounded-md border-2 border-[#7a5739] bg-[#fffaf0] p-4">
              <p className="text-sm font-semibold text-stone-950">
                {section === 'validate' ? 'Validate graph' : section === 'compatibility' ? 'Compatibility test' : 'Tool mock-call check'}
              </p>
              <p className="mt-1 text-xs font-semibold uppercase tracking-[0.16em] text-[#2f9b96]">{statusLabel(results[section])}</p>
              <p className="mt-2 text-sm text-stone-700">{resultSummary(results[section])}</p>
              {activeSection === section && results[section] ? (
                <pre className="mt-3 max-h-64 overflow-auto rounded-md border border-[#7a5739]/30 bg-[#fff6df] p-3 text-xs text-stone-700">
                  {stringifyDiagnostic(results[section])}
                </pre>
              ) : null}
            </article>
          ))}
          <article className="mt-4 rounded-md border-2 border-[#7a5739] bg-[#fffaf0] p-4">
            <p className="text-sm font-semibold text-stone-950">Raw diagnostics</p>
            {activeSection === 'diagnostics' ? (
              <pre className="mt-3 max-h-80 overflow-auto rounded-md bg-stone-50 p-3 text-xs text-stone-700">
                {stringifyDiagnostic(combinedDiagnostics)}
              </pre>
            ) : (
              <p className="mt-2 text-sm text-stone-500">Use View diagnostics to inspect the latest raw diagnostic payloads.</p>
            )}
          </article>
        </section>
        <aside className="border-t-2 border-[#7a5739] bg-[#f8e8c8] p-4 md:border-l-2 md:border-t-0">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#2f9b96]">Test menu</p>
          <div className="mt-4 grid gap-2">
            <button
              type="button"
              disabled={isBusy}
              onClick={() => run('validate', onValidateGraph)}
              className="rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-3 py-2 text-left text-sm font-bold text-[#22170f] hover:bg-[#ffe6b3] disabled:opacity-50"
            >
              Validate graph
            </button>
            <button
              type="button"
              disabled={isBusy}
              onClick={() => run('compatibility', onCompatibilityTest)}
              className="rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-3 py-2 text-left text-sm font-bold text-[#22170f] hover:bg-[#ffe6b3] disabled:opacity-50"
            >
              Compatibility test
            </button>
            <button
              type="button"
              disabled={isBusy}
              onClick={() => run('tools', onToolMockCallCheck)}
              className="rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-3 py-2 text-left text-sm font-bold text-[#22170f] hover:bg-[#ffe6b3] disabled:opacity-50"
            >
              Tool mock-call check
            </button>
            <button
              type="button"
              onClick={() => setActiveSection('diagnostics')}
              className="rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-3 py-2 text-left text-sm font-bold text-[#22170f] hover:bg-[#ffe6b3]"
            >
              View diagnostics
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
}
