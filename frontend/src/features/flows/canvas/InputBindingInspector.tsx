import { useEffect, useMemo, useRef, useState } from 'react';
import type { FlowGraphNodeId, FlowTransferInputType, FlowTransferTransform } from '../flowGraphTypes';
import type { FlowCanvasDraft, PublishedCrewOption } from '../hooks';
import { getOutputFieldOptions, type OutputFieldOption } from './flowCanvasHelpers';
import { buildTransformInputMapping } from './inputBindings';

const inputTypes: FlowTransferInputType[] = ['text', 'structured', 'raw'];
const transforms: FlowTransferTransform[] = [
  'identity_v1',
  'join_text_v1',
  'join_card_news_slides_v1',
  'json_stringify_v1',
];
const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function getFocusableElements(container: HTMLElement) {
  return Array.from(container.querySelectorAll<HTMLElement>(focusableSelector)).filter(
    (element) => !element.hasAttribute('disabled') && element.getAttribute('aria-hidden') !== 'true',
  );
}

function sourcePath(path: string) {
  return path === 'raw' ? 'output.raw' : `output.${path}`;
}

function getAncestorNodeIds(draft: FlowCanvasDraft, targetNodeId: FlowGraphNodeId) {
  const ancestors = new Set<FlowGraphNodeId>();
  const pending: FlowGraphNodeId[] = [targetNodeId];

  while (pending.length > 0) {
    const currentNodeId = pending.pop();
    if (!currentNodeId) {
      continue;
    }

    for (const edge of draft.edges) {
      if (edge.type !== 'flow' || edge.target !== currentNodeId || ancestors.has(edge.source)) {
        continue;
      }

      ancestors.add(edge.source);
      pending.push(edge.source);
    }
  }

  return ancestors;
}

export function InputBindingInspector({
  draft,
  targetNodeId,
  inputName,
  publishedCrews,
  onChangeDraft,
  onClose,
}: {
  draft: FlowCanvasDraft;
  targetNodeId: FlowGraphNodeId;
  inputName: string;
  publishedCrews: PublishedCrewOption[];
  onChangeDraft: (draft: FlowCanvasDraft) => void;
  onClose: () => void;
}) {
  const ancestorNodeIds = useMemo(() => getAncestorNodeIds(draft, targetNodeId), [draft, targetNodeId]);
  const options = useMemo(
    () =>
      getOutputFieldOptions(draft, publishedCrews).filter(
        (option) => option.nodeId !== targetNodeId && ancestorNodeIds.has(option.nodeId),
      ),
    [ancestorNodeIds, draft, publishedCrews, targetNodeId],
  );
  const [selectedOptions, setSelectedOptions] = useState<OutputFieldOption[]>([]);
  const [inputType, setInputType] = useState<FlowTransferInputType>('text');
  const [transform, setTransform] = useState<FlowTransferTransform>(
    inputName === 'card_news_slides' ? 'join_card_news_slides_v1' : 'identity_v1',
  );
  const dialogRef = useRef<HTMLElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const titleId = `input-binding-title-${targetNodeId.replace(/[^a-zA-Z0-9_-]/g, '-')}-${inputName}`;
  const selectedSourceNodeId = selectedOptions[0]?.nodeId;

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

  function toggleOption(option: OutputFieldOption) {
    const isSelected = selectedOptions.some((selectedOption) => selectedOption.value === option.value);

    if (isSelected) {
      setSelectedOptions(selectedOptions.filter((selectedOption) => selectedOption.value !== option.value));
      return;
    }

    if (selectedSourceNodeId && option.nodeId !== selectedSourceNodeId) {
      setSelectedOptions([option]);
      return;
    }

    setSelectedOptions([...selectedOptions, option]);
  }

  function saveBinding() {
    const sourceNodeId = selectedOptions[0]?.nodeId;
    if (!sourceNodeId || selectedOptions.length === 0) {
      return;
    }

    const mapping = buildTransformInputMapping({
      sourceNodeId,
      paths: selectedOptions.map((option) => sourcePath(option.path)),
      inputType,
      transform,
    });

    onChangeDraft({
      ...draft,
      nodes: draft.nodes.map((node) =>
        node.id === targetNodeId
          ? {
              ...node,
              data: {
                ...node.data,
                inputMappings: {
                  ...(isRecord(node.data.inputMappings) ? node.data.inputMappings : {}),
                  [inputName]: mapping,
                },
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
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-rose-700">Input binding</p>
            <h3 id={titleId} className="mt-1 text-base font-semibold text-stone-950">
              Bind {inputName}
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
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="grid gap-1">
              <span className="text-xs font-semibold text-stone-700">Transfer type</span>
              <select
                aria-label="Transfer type"
                value={inputType}
                onChange={(event) => setInputType(event.target.value as FlowTransferInputType)}
                className="rounded-xl border border-stone-300 bg-white px-3 py-2 text-sm font-medium text-stone-900"
              >
                {inputTypes.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-1">
              <span className="text-xs font-semibold text-stone-700">Transform</span>
              <select
                aria-label="Transform"
                value={transform}
                onChange={(event) => setTransform(event.target.value as FlowTransferTransform)}
                className="rounded-xl border border-stone-300 bg-white px-3 py-2 text-sm font-medium text-stone-900"
              >
                {transforms.map((candidate) => (
                  <option key={candidate} value={candidate}>
                    {candidate}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {options.length > 0 ? (
            <div className="grid gap-2">
              {options.map((option) => {
                const checked = selectedOptions.some((selectedOption) => selectedOption.value === option.value);

                return (
                  <label
                    key={option.value}
                    className="flex items-center gap-3 rounded-xl border border-rose-200 bg-white px-3 py-2 text-sm font-semibold text-stone-900"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleOption(option)}
                      className="h-4 w-4 rounded border-stone-300 text-rose-600"
                    />
                    <span>{option.label}</span>
                  </label>
                );
              })}
            </div>
          ) : (
            <p className="rounded-xl border border-dashed border-rose-200 bg-white px-3 py-3 text-sm text-stone-600">
              Add an upstream Crew with an output schema to bind this input.
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
            onClick={saveBinding}
            disabled={selectedOptions.length === 0}
            className="pixel-button bg-rose-500 px-4 py-2 text-sm font-bold text-white hover:bg-rose-400 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Save binding
          </button>
        </div>
      </section>
    </div>
  );
}
