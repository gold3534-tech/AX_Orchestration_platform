import { useEffect, useMemo, useRef, useState, type FocusEvent, type FormEvent, type KeyboardEvent } from 'react';
import { ClipboardList, FileCode, FileOutput, Layers, Settings2, Sparkles, X, Zap } from 'lucide-react';
import {
  FieldGroup,
  NumberInput,
  SchemaBuilder,
  Section,
  SelectInput,
  TextInput,
  Toggle,
} from '../../components/shared/ConfigUI';
import type { components } from '../../types/api.generated';
import { insertPresetTokenOnce, removePresetToken, type TextSelection } from '../inputPresets/presetTokenInsertion';
import { ToolConfigPanel } from '../tools/ToolConfigPanel';
import { ToolPicker } from '../tools/ToolPicker';
import { defaultToolConfig, toolByKey, type ToolConfigsByKey } from '../tools/toolConfig';
import {
  STRUCTURED_EXPECTED_OUTPUT_PLACEHOLDER,
  structuredExpectedOutputFromFields,
  type TaskFormValues,
  type TaskInputPresetOption,
} from './hooks';

type ToolCatalogResponse = components['schemas']['ToolCatalogResponse'];

type TaskModalProps = {
  open: boolean;
  mode: 'create' | 'edit';
  resetKey: string;
  initialValues: TaskFormValues;
  inputPresets: TaskInputPresetOption[];
  availableTools: string[];
  availableToolCatalog: ToolCatalogResponse[];
  taskOptions: string[];
  isSubmitting?: boolean;
  onClose: () => void;
  onSubmit: (values: TaskFormValues) => void | Promise<void>;
};

const outputTypeOptions: NonNullable<TaskFormValues['outputType']>[] = ['Raw', 'Output JSON', 'Output Pydantic'];
const fieldClassName =
  'w-full rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-3 py-2 text-sm text-stone-900 outline-none transition placeholder:text-stone-400 focus:border-[#2f9b96] focus:ring-2 focus:ring-[#2f9b96]/25 disabled:cursor-not-allowed disabled:bg-[#f8e8c8]';
const identifierPattern = /^[A-Za-z_][A-Za-z0-9_]*$/;
const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

function normalizeToolConfigsForSelection(
  toolKeys: string[] = [],
  currentConfigs: ToolConfigsByKey | undefined,
  catalogByKey: Map<string, ToolCatalogResponse>,
): ToolConfigsByKey {
  return Object.fromEntries(
    toolKeys.map((toolKey) => {
      const tool = catalogByKey.get(toolKey);
      const existingConfig = currentConfigs?.[toolKey] ?? {};
      return [toolKey, tool ? { ...defaultToolConfig(tool), ...existingConfig } : { ...existingConfig }] as const;
    }),
  );
}

function cloneValues(values: TaskFormValues, catalogByKey: Map<string, ToolCatalogResponse>): TaskFormValues {
  const tools = [...(values.tools ?? [])];

  return {
    name: values.name ?? '',
    description: values.description ?? '',
    expectedOutput: values.expectedOutput ?? '',
    outputType: values.outputType ?? 'Raw',
    outputSchemaFields: values.outputType === 'Raw' ? [] : [...(values.outputSchemaFields ?? [])],
    asyncExecution: values.asyncExecution,
    humanInput: values.humanInput,
    markdown: values.markdown,
    guardrailMaxRetries: values.guardrailMaxRetries,
    outputFile: values.outputFile ?? '',
    createDirectory: values.createDirectory,
    inputPresets: [...(values.inputPresets ?? [])],
    tools,
    toolConfigs: normalizeToolConfigsForSelection(tools, values.toolConfigs, catalogByKey),
  };
}

function SelectedPresetChip({
  preset,
  onRemove,
}: {
  preset: TaskInputPresetOption;
  onRemove: (key: string) => void;
}) {
  return (
    <div className="rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-3 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="m-0 text-sm font-bold text-[#22170f]">{preset.label}</p>
          <p className="m-0 mt-1 text-xs text-stone-500">{preset.key}</p>
          {preset.description ? <p className="m-0 mt-1 text-xs leading-5 text-stone-600">{preset.description}</p> : null}
        </div>
        <button
          type="button"
          onClick={() => onRemove(preset.key)}
          className="shrink-0 rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-2.5 py-1 text-xs font-bold text-stone-700 hover:bg-[#ffe6b3]"
        >
          Remove
        </button>
      </div>
    </div>
  );
}

function hasValidStructuredSchema(values: TaskFormValues) {
  const fields = values.outputSchemaFields ?? [];

  return fields.length > 0 && fields.every((field) => identifierPattern.test(field.name.trim()));
}

function expectedOutputPlaceholder(outputType: TaskFormValues['outputType']) {
  return (outputType ?? 'Raw') === 'Raw' ? 'Specify the completed result...' : STRUCTURED_EXPECTED_OUTPUT_PLACEHOLDER;
}

function valuesWithExpectedOutputDefault(values: TaskFormValues): TaskFormValues {
  if ((values.outputType ?? 'Raw') === 'Raw' || values.expectedOutput.trim().length > 0) {
    return values;
  }

  return {
    ...values,
    expectedOutput: structuredExpectedOutputFromFields(values.outputSchemaFields),
  };
}

function getFocusableElements(container: HTMLElement) {
  return Array.from(container.querySelectorAll<HTMLElement>(focusableSelector)).filter(
    (element) => element.getAttribute('aria-hidden') !== 'true',
  );
}

export function TaskModal({
  open,
  mode,
  resetKey,
  initialValues,
  inputPresets,
  availableTools,
  availableToolCatalog,
  taskOptions,
  isSubmitting = false,
  onClose,
  onSubmit,
}: TaskModalProps) {
  const dialogRef = useRef<HTMLFormElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const previousOpenRef = useRef(false);
  const lastResetKeyRef = useRef<string | null>(null);
  const descriptionRef = useRef<HTMLTextAreaElement>(null);
  const expectedOutputRef = useRef<HTMLTextAreaElement>(null);
  const presetSelectRef = useRef<HTMLSelectElement>(null);
  const lastBodyTargetRef = useRef<{
    field: 'description' | 'expectedOutput';
    selection: TextSelection | null;
  } | null>(null);
  const availableToolByKey = useMemo(() => toolByKey(availableToolCatalog), [availableToolCatalog]);
  const [values, setValues] = useState<TaskFormValues>(() => cloneValues(initialValues, availableToolByKey));

  useEffect(() => {
    const wasOpen = previousOpenRef.current;
    let focusTimer: number | undefined;

    if (open) {
      if (!wasOpen) {
        previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      }

      if (!wasOpen || lastResetKeyRef.current !== resetKey) {
        setValues(cloneValues(initialValues, availableToolByKey));
        lastBodyTargetRef.current = null;
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
  }, [availableToolByKey, initialValues, open, resetKey]);

  const presetMap = useMemo(() => new Map(inputPresets.map((preset) => [preset.key, preset])), [inputPresets]);
  const selectedPresets = values.inputPresets
    .map((key) => presetMap.get(key))
    .filter((preset): preset is TaskInputPresetOption => Boolean(preset));
  const availablePresets = inputPresets.filter((preset) => !values.inputPresets.includes(preset.key));
  const canSubmit =
    !isSubmitting &&
    values.name.trim().length > 0 &&
    values.description.trim().length > 0 &&
    ((values.outputType ?? 'Raw') === 'Raw' ? values.expectedOutput.trim().length > 0 : hasValidStructuredSchema(values));

  if (!open) {
    return null;
  }

  function updateValue<K extends keyof TaskFormValues>(key: K, value: TaskFormValues[K]) {
    setValues((current) => {
      if (key === 'outputType' && value === 'Raw') {
        return { ...current, outputType: 'Raw', outputSchemaFields: [] };
      }

      return { ...current, [key]: value };
    });
  }

  function activeBodyField(): 'description' | 'expectedOutput' | null {
    if (document.activeElement === descriptionRef.current) return 'description';
    if (document.activeElement === expectedOutputRef.current) return 'expectedOutput';
    return null;
  }

  function rememberBodyTarget(field: 'description' | 'expectedOutput', selection: TextSelection | null = null) {
    lastBodyTargetRef.current = { field, selection };
  }

  function rememberBodySelection(field: 'description' | 'expectedOutput', element: HTMLTextAreaElement) {
    rememberBodyTarget(field, { start: element.selectionStart, end: element.selectionEnd });
  }

  function clearBodyTarget() {
    lastBodyTargetRef.current = null;
  }

  function handleFocusCapture(event: FocusEvent<HTMLFormElement>) {
    const target = event.target as HTMLElement;
    if (
      target === descriptionRef.current ||
      target === expectedOutputRef.current ||
      target === presetSelectRef.current
    ) {
      return;
    }

    clearBodyTarget();
  }

  function addInputPreset(key: string) {
    if (!key || values.inputPresets.includes(key)) {
      return;
    }

    const activeField = activeBodyField();
    const target = activeField
      ? { field: activeField, selection: lastBodyTargetRef.current?.field === activeField ? lastBodyTargetRef.current.selection : null }
      : lastBodyTargetRef.current;
    const targetField = target?.field ?? 'description';
    setValues((current) => ({
      ...current,
      [targetField]: insertPresetTokenOnce(current[targetField], key, target?.selection ?? null),
      inputPresets: [...current.inputPresets, key],
    }));
  }

  function removeInputPreset(key: string) {
    setValues((current) => ({
      ...current,
      description: removePresetToken(current.description, key),
      expectedOutput: removePresetToken(current.expectedOutput, key),
      inputPresets: current.inputPresets.filter((preset) => preset !== key),
    }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }

    const normalizedValues = {
      ...values,
      toolConfigs: normalizeToolConfigsForSelection(values.tools ?? [], values.toolConfigs, availableToolByKey),
    };
    await onSubmit(valuesWithExpectedOutputDefault(normalizedValues));
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
        aria-label="Configure Task"
        aria-modal="true"
        tabIndex={-1}
        onSubmit={handleSubmit}
        onFocusCapture={handleFocusCapture}
        onKeyDown={handleKeyDown}
        className="relative flex h-[85vh] w-full max-w-[1300px] flex-col overflow-hidden rounded-md border-2 border-[#7a5739] bg-[#fff6df] text-stone-900 shadow-[8px_8px_0_#7a5739]"
      >
        <div className="flex items-center justify-between gap-4 border-b-2 border-[#7a5739] bg-[#f8e8c8] px-6 py-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="rounded-md border-2 border-[#7a5739] bg-[#e6f6f2] p-2 shadow-[2px_2px_0_#7a5739]">
              <ClipboardList aria-hidden="true" className="h-5 w-5 text-[#2f9b96]" />
            </div>
            <div className="min-w-0">
              <h2 className="text-lg font-black text-[#22170f]">Configure Task</h2>
              <p className="m-0 text-xs font-medium uppercase tracking-wide text-stone-500">
                {mode === 'create' ? 'New task' : 'Editing task'}
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
          <div className="min-w-0 flex-[0.9] space-y-6 overflow-y-auto overflow-x-hidden border-b-2 border-[#7a5739] p-6 lg:border-b-0 lg:border-r-2">
            <section className="min-w-0 space-y-4">
              <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-[#2f9b96]">
                <Sparkles aria-hidden="true" className="h-4 w-4 text-[#2f9b96]" />
                Task Definition
              </h3>
              <div className="max-w-md">
                <FieldGroup label="Name">
                  <TextInput
                    ariaLabel="Name"
                    value={values.name}
                    onChange={(value) => updateValue('name', value)}
                    placeholder="Enter task name..."
                  />
                </FieldGroup>
              </div>
              <FieldGroup label="Description">
                <textarea
                  aria-label="Description"
                  ref={descriptionRef}
                  value={values.description}
                  onFocus={() => rememberBodyTarget('description')}
                  onClick={(event) => rememberBodySelection('description', event.currentTarget)}
                  onKeyUp={(event) => rememberBodySelection('description', event.currentTarget)}
                  onSelect={(event) => rememberBodySelection('description', event.currentTarget)}
                  onChange={(event) => updateValue('description', event.target.value)}
                  rows={4}
                  placeholder="Provide detailed instructions for the agent..."
                  className={`${fieldClassName} min-h-28 resize-y leading-6`}
                />
              </FieldGroup>
              <ToolPicker
                tools={availableTools}
                selectedTools={values.tools ?? []}
                onChange={(nextTools) => {
                  setValues((current) => {
                    return {
                      ...current,
                      tools: nextTools,
                      toolConfigs: normalizeToolConfigsForSelection(nextTools, current.toolConfigs, availableToolByKey),
                    };
                  });
                }}
              />
              <ToolConfigPanel
                tools={availableToolCatalog}
                selectedToolKeys={values.tools ?? []}
                toolConfigs={values.toolConfigs ?? {}}
                onChange={(toolKey, config) => {
                  setValues((current) => ({
                    ...current,
                    toolConfigs: {
                      ...(current.toolConfigs ?? {}),
                      [toolKey]: config,
                    },
                  }));
                }}
              />
            </section>
          </div>

          <div className="min-w-0 flex-1 space-y-6 overflow-y-auto border-b-2 border-[#7a5739] bg-[#f8e8c8]/45 p-6 lg:border-b-0 lg:border-r-2">
            <section className="space-y-4">
              <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-[#2f9b96]">
                <FileCode aria-hidden="true" className="h-4 w-4 text-[#2f9b96]" />
                Expected Output
              </h3>
              <SelectInput
                label="Output Type"
                options={outputTypeOptions}
                value={values.outputType}
                onChange={(value) => updateValue('outputType', value as TaskFormValues['outputType'])}
              />

              <FieldGroup
                label="Expected output"
                helperText={
                  (values.outputType ?? 'Raw') === 'Raw'
                    ? 'Define the raw text structure or completion criteria.'
                    : 'Describe the structured output contract in natural language.'
                }
              >
                <textarea
                  aria-label="Expected output"
                  ref={expectedOutputRef}
                  value={values.expectedOutput}
                  onFocus={() => rememberBodyTarget('expectedOutput')}
                  onClick={(event) => rememberBodySelection('expectedOutput', event.currentTarget)}
                  onKeyUp={(event) => rememberBodySelection('expectedOutput', event.currentTarget)}
                  onSelect={(event) => rememberBodySelection('expectedOutput', event.currentTarget)}
                  onChange={(event) => updateValue('expectedOutput', event.target.value)}
                  rows={4}
                  placeholder={expectedOutputPlaceholder(values.outputType)}
                  className={`${fieldClassName} min-h-28 resize-y leading-6`}
                />
              </FieldGroup>

              {(values.outputType ?? 'Raw') !== 'Raw' ? (
                <SchemaBuilder
                  fields={values.outputSchemaFields ?? []}
                  onChange={(fields) => updateValue('outputSchemaFields', fields)}
                />
              ) : null}
            </section>
          </div>

          <aside className="w-full shrink-0 overflow-y-auto bg-[#f8e8c8]/70 lg:w-[340px]">
            <Section title="Input Preset" icon={Sparkles}>
              <FieldGroup label="Input presets" helperText="Insert preset tokens into the active text field.">
                <select
                  aria-label="Input presets"
                  ref={presetSelectRef}
                  value=""
                  onChange={(event) => {
                    addInputPreset(event.target.value);
                    event.target.value = '';
                  }}
                  className="w-full rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-3 py-2 text-sm text-stone-900"
                >
                  <option value="">Select an input preset</option>
                  {availablePresets.map((preset) => (
                    <option key={preset.key} value={preset.key}>
                      {preset.label}
                    </option>
                  ))}
                </select>
              </FieldGroup>
              {selectedPresets.length > 0 ? (
                <div className="grid gap-3">
                  {selectedPresets.map((preset) => (
                    <SelectedPresetChip key={preset.key} preset={preset} onRemove={removeInputPreset} />
                  ))}
                </div>
              ) : (
                <div className="rounded-md border-2 border-dashed border-[#7a5739] bg-[#fffaf0] px-3 py-4 text-sm text-stone-500">
                  No presets added yet.
                </div>
              )}
            </Section>

            <Section title="Execution" icon={Zap} defaultOpen={false}>
              <Toggle
                label="Async Execution"
                value={values.asyncExecution}
                onChange={(value) => updateValue('asyncExecution', value)}
              />
              <Toggle label="Human Input" value={values.humanInput} onChange={(value) => updateValue('humanInput', value)} />
            </Section>

            <Section title="File Settings" icon={FileOutput} defaultOpen={false}>
              <Toggle
                label="Markdown Output"
                description="Required for .md report generation"
                value={values.markdown}
                onChange={(value) => updateValue('markdown', value)}
              />
              <Toggle
                label="Create Directory"
                description="Create missing directories for output files"
                value={values.createDirectory}
                onChange={(value) => updateValue('createDirectory', value)}
              />
              <FieldGroup label="Output File">
                <TextInput
                  value={values.outputFile}
                  onChange={(value) => updateValue('outputFile', value)}
                  placeholder={values.markdown ? 'reports/analysis.md' : 'data/results.json'}
                />
              </FieldGroup>
            </Section>

            <Section title="Advanced" icon={Settings2} defaultOpen={false}>
              <FieldGroup label="Guardrail Max Retries">
                <NumberInput
                  value={values.guardrailMaxRetries}
                  onChange={(value) => updateValue('guardrailMaxRetries', value)}
                  placeholder="Backend default"
                />
              </FieldGroup>
              <div className="rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-3 py-3">
                <h3 className="m-0 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-stone-500">
                  <Layers aria-hidden="true" className="h-3.5 w-3.5" />
                  Available Task Contexts
                </h3>
                <p className="m-0 mt-2 text-xs leading-5 text-stone-500">
                  {taskOptions.length > 0 ? taskOptions.join(', ') : 'No peer tasks available.'}
                </p>
              </div>
            </Section>
          </aside>
        </div>

        <div className="flex items-center justify-between gap-4 border-t-2 border-[#7a5739] bg-[#f8e8c8] px-6 py-4">
          <p className="m-0 text-xs italic text-stone-500">Unset runtime values will use backend defaults.</p>
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
              {mode === 'create' ? 'Create task' : 'Save Configuration'}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
