import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { Activity, Database, LayoutPanelTop, Settings2, Sparkles, Users, X, Zap } from 'lucide-react';
import {
  FieldGroup,
  NumberInput,
  Section,
  TextInput,
  Toggle,
} from '../../components/shared/ConfigUI';
import { DEFAULT_HIERARCHICAL_MANAGER_LLM, type CrewFormValues, type CrewLibraryOption } from './hooks';

type CrewModalProps = {
  open: boolean;
  mode: 'create' | 'edit';
  resetKey: string;
  initialValues: CrewFormValues;
  availableAgents: CrewLibraryOption[];
  isSubmitting?: boolean;
  onClose: () => void;
  onSubmit: (values: CrewFormValues) => void | Promise<void>;
};

const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

function cloneValues(values: CrewFormValues): CrewFormValues {
  return {
    ...values,
    canvasDraft: {
      selectedNodeId: values.canvasDraft.selectedNodeId,
      nodes: values.canvasDraft.nodes.map((node) => ({ ...node })),
      edges: values.canvasDraft.edges.map((edge) => ({ ...edge })),
      insertionOrder: [...values.canvasDraft.insertionOrder],
      nodePositions: { ...values.canvasDraft.nodePositions },
      nodeSizes: { ...(values.canvasDraft.nodeSizes ?? {}) },
    },
  };
}

function getFocusableElements(container: HTMLElement) {
  return Array.from(container.querySelectorAll<HTMLElement>(focusableSelector)).filter(
    (element) => element.getAttribute('aria-hidden') !== 'true',
  );
}

export function CrewModal({
  open,
  mode,
  resetKey,
  initialValues,
  availableAgents,
  isSubmitting = false,
  onClose,
  onSubmit,
}: CrewModalProps) {
  const dialogRef = useRef<HTMLFormElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const previousOpenRef = useRef(false);
  const lastResetKeyRef = useRef<string | null>(null);
  const [values, setValues] = useState<CrewFormValues>(() => cloneValues(initialValues));

  useEffect(() => {
    const wasOpen = previousOpenRef.current;
    let focusTimer: number | undefined;

    if (open) {
      if (!wasOpen) {
        previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      }

      if (!wasOpen || lastResetKeyRef.current !== resetKey) {
        setValues(cloneValues(initialValues));
        lastResetKeyRef.current = resetKey;
      }

      focusTimer = window.setTimeout(() => {
        dialogRef.current?.focus();
      }, 0);
    } else if (wasOpen) {
      previousFocusRef.current?.focus();
      previousFocusRef.current = null;
    }

    previousOpenRef.current = open;

    return () => {
      if (focusTimer !== undefined) {
        window.clearTimeout(focusTimer);
      }
    };
  }, [initialValues, open, resetKey]);

  if (!open) {
    return null;
  }

  const canSubmit = !isSubmitting && values.name.trim().length > 0;

  function updateValue<K extends keyof CrewFormValues>(key: K, value: CrewFormValues[K]) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  function updateProcess(process: CrewFormValues['process']) {
    setValues((current) => ({
      ...current,
      process,
      managerLlm:
        process === 'hierarchical' && !current.managerLlm.trim()
          ? DEFAULT_HIERARCHICAL_MANAGER_LLM
          : current.managerLlm,
    }));
  }

  function valuesForSubmit() {
    if (values.process !== 'hierarchical' || values.managerLlm.trim()) {
      return values;
    }

    return { ...values, managerLlm: DEFAULT_HIERARCHICAL_MANAGER_LLM };
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }

    await onSubmit(valuesForSubmit());
  }

  function handleKeyDown(event: KeyboardEvent<HTMLFormElement>) {
    if (event.key === 'Tab') {
      const focusableElements = getFocusableElements(event.currentTarget);
      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];

      if (!firstElement || !lastElement) {
        event.preventDefault();
        return;
      }

      if (event.shiftKey && document.activeElement === firstElement) {
        event.preventDefault();
        lastElement.focus();
      } else if (!event.shiftKey && document.activeElement === lastElement) {
        event.preventDefault();
        firstElement.focus();
      }

      return;
    }

    if (event.key !== 'Escape') {
      return;
    }

    event.stopPropagation();
    if (isSubmitting) {
      return;
    }

    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-[#22170f]/50 backdrop-blur-sm" aria-hidden="true" />

      <form
        ref={dialogRef}
        role="dialog"
        aria-label="Configure Crew"
        aria-modal="true"
        tabIndex={-1}
        onSubmit={handleSubmit}
        onKeyDown={handleKeyDown}
        className="relative flex h-[85vh] w-full max-w-[1100px] flex-col overflow-hidden rounded-md border-2 border-[#7a5739] bg-[#fff6df] text-stone-900 shadow-[8px_8px_0_#7a5739]"
      >
        <div className="flex items-center justify-between gap-4 border-b-2 border-[#7a5739] bg-[#f8e8c8] px-6 py-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="rounded-md border-2 border-[#7a5739] bg-[#e6f6f2] p-2 shadow-[2px_2px_0_#7a5739]">
              <Users aria-hidden="true" className="h-5 w-5 text-[#2f9b96]" />
            </div>
            <div className="min-w-0">
              <h2 className="text-lg font-black text-[#22170f]">Configure Crew</h2>
              <p className="m-0 text-xs font-medium uppercase tracking-wide text-stone-500">
                {mode === 'create' ? 'New crew' : 'Runtime settings'}
              </p>
            </div>
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            disabled={isSubmitting}
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border-2 border-[#7a5739] bg-[#fffaf0] text-stone-600 transition hover:bg-[#ffe6b3] hover:text-stone-900 disabled:opacity-50"
          >
            <X aria-hidden="true" className="h-5 w-5" />
          </button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden lg:flex-row">
          <div className="min-w-0 flex-1 space-y-6 overflow-y-auto border-b-2 border-[#7a5739] p-6 lg:border-b-0 lg:border-r-2">
            <section className="space-y-4">
              <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-[#2f9b96]">
                <Sparkles aria-hidden="true" className="h-4 w-4 text-[#2f9b96]" />
                Crew Overview
              </h3>
              <FieldGroup label="Crew Name">
                <TextInput
                  ariaLabel="Crew Name"
                  value={values.name}
                  onChange={(value) => updateValue('name', value)}
                  placeholder="Content generation crew"
                />
              </FieldGroup>
              <FieldGroup label="Description">
                <TextInput
                  ariaLabel="Description"
                  value={values.description}
                  onChange={(value) => updateValue('description', value)}
                  multiline
                  placeholder="Describe when this runtime preset should be used..."
                />
              </FieldGroup>
            </section>

            <section className="space-y-4 border-t-2 border-[#7a5739]/40 pt-6">
              <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-[#2f9b96]">
                <LayoutPanelTop aria-hidden="true" className="h-4 w-4 text-[#2f9b96]" />
                Orchestration
              </h3>
              <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_12rem]">
                <FieldGroup
                  label="Process"
                  helperText={values.process === 'hierarchical' ? 'Manager settings apply to hierarchical runs.' : 'Runs canvas tasks in order.'}
                >
                  <div className="inline-flex rounded-md border-2 border-[#7a5739] bg-[#f8e8c8] p-1">
                    {(['sequential', 'hierarchical'] as const).map((process) => (
                      <button
                        key={process}
                        type="button"
                        aria-pressed={values.process === process}
                        onClick={() => updateProcess(process)}
                        className={`rounded px-4 py-2 text-xs font-bold uppercase transition ${
                          values.process === process
                            ? 'bg-[#2f9b96] text-white shadow-sm'
                            : 'text-stone-500 hover:text-stone-800'
                        }`}
                      >
                        {process}
                      </button>
                    ))}
                  </div>
                </FieldGroup>
                <FieldGroup label="Max RPM" helperText="Global request limit.">
                  <NumberInput
                    value={values.maxRpm}
                    onChange={(value) => updateValue('maxRpm', value)}
                    placeholder="No limit"
                  />
                </FieldGroup>
              </div>

              {values.process === 'hierarchical' ? (
                <div className="space-y-3 rounded-md border-2 border-[#7a5739] bg-[#fffaf0] p-4">
                  <div className="grid gap-4 md:grid-cols-2">
                    <FieldGroup label="Manager Agent" helperText="Reserved for a later hierarchical runtime phase.">
                      <select
                        aria-label="Manager Agent"
                        value={values.managerAgentAssetId}
                        onChange={(event) => updateValue('managerAgentAssetId', event.target.value)}
                        disabled
                        className="w-full rounded-md border-2 border-[#7a5739] bg-[#f8e8c8] px-3 py-2 text-sm text-stone-500 outline-none transition disabled:cursor-not-allowed disabled:opacity-70"
                      >
                        <option value="">Manager LLM only for now</option>
                        {availableAgents.map((agent) => (
                          <option key={agent.assetId} value={agent.assetId}>
                            {agent.name}
                          </option>
                        ))}
                      </select>
                    </FieldGroup>
                    <FieldGroup label="Manager LLM">
                      <TextInput
                        value={values.managerLlm}
                        onChange={(value) => updateValue('managerLlm', value)}
                        placeholder="gpt-4o-mini"
                      />
                    </FieldGroup>
                  </div>
                </div>
              ) : null}
            </section>
          </div>

          <aside className="w-full shrink-0 overflow-y-auto bg-[#f8e8c8]/70 lg:w-[350px]">
            <Section title="Monitoring" icon={Activity}>
              <Toggle
                label="Verbose"
                description="Show detailed execution logs."
                value={values.verbose}
                onChange={(value) => updateValue('verbose', value)}
              />
              <Toggle
                label="Stream"
                description="Stream run output where supported."
                value={values.stream}
                onChange={(value) => updateValue('stream', value)}
              />
              <Toggle
                label="Tracing"
                description="Record trace metadata for runs."
                value={values.tracing}
                onChange={(value) => updateValue('tracing', value)}
              />
              <FieldGroup label="Output Log File">
                <TextInput
                  value={values.outputLogFile}
                  onChange={(value) => updateValue('outputLogFile', value)}
                  placeholder="crew.log"
                />
              </FieldGroup>
            </Section>

            <Section title="Advanced" icon={Settings2} defaultOpen={false}>
              <Toggle
                label="Planning"
                description="Let the crew plan before execution."
                value={values.planning}
                onChange={(value) => updateValue('planning', value)}
              />
              <Toggle
                label="Cache"
                description="Reuse compatible runtime work."
                value={values.cache}
                onChange={(value) => updateValue('cache', value)}
              />
              <FieldGroup label="Function Calling LLM">
                <TextInput
                  value={values.functionCallingLlm}
                  onChange={(value) => updateValue('functionCallingLlm', value)}
                  placeholder="CrewAI native default"
                />
              </FieldGroup>
              <FieldGroup label="Planning LLM">
                <TextInput
                  value={values.planningLlm}
                  onChange={(value) => updateValue('planningLlm', value)}
                  placeholder="CrewAI native default"
                />
              </FieldGroup>
              <FieldGroup label="Chat LLM">
                <TextInput
                  value={values.chatLlm}
                  onChange={(value) => updateValue('chatLlm', value)}
                  placeholder="CrewAI native default"
                />
              </FieldGroup>
            </Section>

            <Section title="Memory" icon={Database} defaultOpen={false}>
              <Toggle
                label="Memory"
                description="Enable memory for this crew."
                value={values.memory}
                onChange={(value) => updateValue('memory', value)}
              />
              <Toggle
                label="Checkpoint"
                description="Persist execution checkpoints."
                value={values.checkpoint}
                onChange={(value) => updateValue('checkpoint', value)}
              />
              <FieldGroup label="Embedder">
                <TextInput
                  value={values.embedder}
                  onChange={(value) => updateValue('embedder', value)}
                  placeholder="CrewAI native default"
                />
              </FieldGroup>
            </Section>

            <Section title="Runtime" icon={Zap} defaultOpen={false}>
              <p className="m-0 rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-3 py-3 text-xs leading-5 text-stone-500">
                Crew tasks, selected agents, and task ordering are managed in the builder canvas.
              </p>
            </Section>
          </aside>
        </div>

        <div className="flex items-center justify-between gap-4 border-t-2 border-[#7a5739] bg-[#f8e8c8] px-6 py-4">
          <p className="m-0 text-xs italic text-stone-500">Unset runtime values use CrewAI native defaults.</p>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="pixel-button border-[#7a5739] bg-[#fffaf0] px-4 py-2 text-sm font-bold text-[#22170f] transition hover:bg-[#ffe6b3] disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!canSubmit}
              className="pixel-button bg-[#2f9b96] px-5 py-2 text-sm font-bold text-white transition hover:bg-[#3fb0aa] disabled:cursor-not-allowed disabled:bg-stone-300 disabled:text-stone-500"
            >
              Save Configuration
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
