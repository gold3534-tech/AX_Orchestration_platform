import { useEffect, useRef, useState } from 'react';
import type { FlowCanvasDraft, PublishedCrewOption } from '../hooks';
import { getOutputFieldOptions, type OutputFieldOption } from './flowCanvasHelpers';

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

export function OutputFieldsInspector({
  draft,
  outputNode,
  publishedCrews,
  onChangeDraft,
  onClose,
}: {
  draft: FlowCanvasDraft;
  outputNode: FlowCanvasDraft['nodes'][number];
  publishedCrews: PublishedCrewOption[];
  onChangeDraft: (draft: FlowCanvasDraft) => void;
  onClose: () => void;
}) {
  const options = getOutputFieldOptions(draft, publishedCrews);
  const [selectedValue, setSelectedValue] = useState(options[0]?.value ?? '');
  const [fields, setFields] = useState<Array<Record<string, unknown>>>(() =>
    Array.isArray(outputNode.data.fields) ? outputNode.data.fields : [],
  );
  const dialogRef = useRef<HTMLElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

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
    function handleDocumentKeyDown(event: KeyboardEvent) {
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

    document.addEventListener('keydown', handleDocumentKeyDown);

    return () => {
      document.removeEventListener('keydown', handleDocumentKeyDown);
    };
  }, [onClose]);

  useEffect(() => {
    if (!selectedValue && options[0]) {
      setSelectedValue(options[0].value);
    }
  }, [options, selectedValue]);

  function saveFields() {
    onChangeDraft({
      ...draft,
      nodes: draft.nodes.map((node) =>
        node.id === outputNode.id
          ? {
              ...node,
              data: {
                ...node.data,
                fields,
              },
            }
          : node,
      ),
    });
    onClose();
  }

  function addSelectedField() {
    const option = options.find((candidate) => candidate.value === selectedValue);
    if (!option) {
      return;
    }

    const nextField = {
      label: option.label,
      source: 'node',
      nodeId: option.nodeId,
      path: option.path === 'raw' ? 'output.raw' : `output.${option.path}`,
    };
    const exists = fields.some(
      (field) =>
        field.source === nextField.source &&
        field.nodeId === nextField.nodeId &&
        field.path === nextField.path,
    );

    if (!exists) {
      setFields([...fields, nextField]);
    }
  }

  function removeField(indexToRemove: number) {
    setFields(fields.filter((_field, index) => index !== indexToRemove));
  }

  function toggleOption(option: OutputFieldOption) {
    const nextField = {
      label: option.label,
      source: 'node',
      nodeId: option.nodeId,
      path: option.path === 'raw' ? 'output.raw' : `output.${option.path}`,
    };
    const existingIndex = fields.findIndex(
      (field) =>
        field.source === nextField.source &&
        field.nodeId === nextField.nodeId &&
        field.path === nextField.path,
    );

    if (existingIndex >= 0) {
      removeField(existingIndex);
      return;
    }

    setFields([...fields, nextField]);
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-stone-950/30 p-4">
      <section
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="output-fields-title"
        tabIndex={-1}
        className="w-full max-w-xl rounded-md border-2 border-[#7a5739] bg-[#fff6df] p-5 shadow-[6px_6px_0_#7a5739]"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-emerald-700">Selected output</p>
            <h3 id="output-fields-title" className="mt-1 text-base font-semibold text-stone-950">
              Select output fields
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

        <div className="mt-4">
          {options.length > 0 ? (
            <div className="grid gap-2">
              {options.map((option) => {
                const fieldPath = option.path === 'raw' ? 'output.raw' : `output.${option.path}`;
                const checked = fields.some(
                  (field) => field.source === 'node' && field.nodeId === option.nodeId && field.path === fieldPath,
                );

                return (
                  <label
                    key={option.value}
                    className="flex items-center gap-3 rounded-xl border border-emerald-200 bg-white px-3 py-2 text-sm font-semibold text-stone-900"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => {
                        setSelectedValue(option.value);
                        toggleOption(option);
                      }}
                      className="h-4 w-4 rounded border-stone-300 text-emerald-600"
                    />
                    <span>{option.label}</span>
                  </label>
                );
              })}
            </div>
          ) : (
            <p className="mt-3 rounded-xl border border-dashed border-emerald-200 bg-white px-3 py-3 text-sm text-stone-600">
              Add a published Crew to select output fields. Raw output is available for each Crew node.
            </p>
          )}

          <div className="mt-3 flex flex-wrap items-end gap-2">
            <label className="grid gap-1">
              <span className="text-xs font-semibold text-stone-700">Output field</span>
              <select
                aria-label="Output field"
                value={selectedValue}
                onChange={(event) => setSelectedValue(event.target.value)}
                className="min-w-64 rounded-xl border border-stone-300 bg-white px-3 py-2 text-sm font-medium text-stone-900"
              >
                {options.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={addSelectedField}
              disabled={options.length === 0}
              className="pixel-button bg-[#2f9b96] px-4 py-2 text-sm font-bold text-white hover:bg-[#3fb0aa] disabled:cursor-not-allowed disabled:opacity-50"
            >
              Add field
            </button>
          </div>

          {fields.length > 0 ? (
            <div className="mt-3 grid gap-2">
              {fields.map((field, index) => (
                <div
                  key={`${field.nodeId ?? 'field'}:${field.path ?? index}`}
                  className="flex items-center justify-between gap-3 rounded-xl border border-emerald-200 bg-white px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-stone-900">
                      {String(field.label ?? field.path ?? 'Output field')}
                    </p>
                    <p className="truncate text-xs text-stone-500">
                      {String(field.nodeId ?? field.source ?? '')} · {String(field.path ?? '')}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeField(index)}
                    className="pixel-button border-[#7a5739] bg-[#fffaf0] px-3 py-1 text-xs font-bold text-[#22170f] hover:bg-[#ffe6b3]"
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-3 rounded-xl border border-dashed border-emerald-200 bg-white px-3 py-3 text-sm text-stone-600">
              No output fields selected yet.
            </p>
          )}
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
            onClick={saveFields}
            className="pixel-button bg-[#2f9b96] px-4 py-2 text-sm font-bold text-white hover:bg-[#3fb0aa]"
          >
            Save fields
          </button>
        </div>
      </section>
    </div>
  );
}
