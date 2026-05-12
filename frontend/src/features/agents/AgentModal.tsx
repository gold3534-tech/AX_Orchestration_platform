import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { BookOpen, Bot, Clock, Cpu, DollarSign, Sparkles, Wrench, X, Zap } from 'lucide-react';
import {
  FieldGroup,
  MultiSelector,
  NumberInput,
  Section,
  SelectInput,
  SliderInput,
  TextInput,
  Toggle,
} from '../../components/shared/ConfigUI';
import type { components } from '../../types/api.generated';
import { ToolConfigPanel } from '../tools/ToolConfigPanel';
import { defaultToolConfig, toolByKey, type ToolConfigsByKey } from '../tools/toolConfig';
import type { AgentAttachmentValues, AgentFormValues, AgentKnowledgeSourceOption } from './hooks';
import {
  findModelOption,
  inferProviderFromModelOption,
  numericDefault,
  parameterSpec,
  type LLMModelOption,
} from './llmCatalog';

type ToolCatalogResponse = components['schemas']['ToolCatalogResponse'];
type AttachmentListKey = 'tools' | 'knowledgeSources';

type AgentModalProps = {
  open: boolean;
  mode: 'create' | 'edit';
  resetKey: string;
  initialValues: AgentFormValues;
  availableTools: ToolCatalogResponse[];
  availableKnowledgeSources: AgentKnowledgeSourceOption[];
  initialAttachments?: AgentAttachmentValues;
  llmModels: LLMModelOption[];
  embedders: string[];
  isSubmitting?: boolean;
  onClose: () => void;
  onSubmit: (values: AgentFormValues, attachments: AgentAttachmentValues) => void | Promise<void>;
};

function clampNumber(value: number, min: number | undefined, max: number | undefined) {
  let nextValue = value;

  if (min !== undefined && nextValue < min) {
    nextValue = min;
  }

  if (max !== undefined && nextValue > max) {
    nextValue = max;
  }

  return nextValue;
}

function isInRange(value: number, min: number | undefined, max: number | undefined) {
  return (min === undefined || value >= min) && (max === undefined || value <= max);
}

function hasBoundedParameterSpec(modelOption: LLMModelOption | undefined, parameter: 'temperature' | 'max_tokens') {
  const spec = parameterSpec(modelOption, parameter);

  return spec?.supported === true && spec.min !== undefined && spec.max !== undefined;
}

function hasVisibleTemperatureControl(modelOption: LLMModelOption | undefined, currentValue: number | undefined) {
  if (!hasBoundedParameterSpec(modelOption, 'temperature')) {
    return false;
  }

  return currentValue !== undefined || numericDefault(modelOption, 'temperature') !== undefined;
}

function normalizedParameterValue(
  currentValue: number | undefined,
  modelOption: LLMModelOption,
  parameter: 'temperature' | 'max_tokens',
) {
  if (!hasBoundedParameterSpec(modelOption, parameter)) {
    return undefined;
  }

  const spec = parameterSpec(modelOption, parameter);
  const defaultValue = numericDefault(modelOption, parameter);

  if (currentValue !== undefined) {
    return clampNumber(currentValue, spec?.min, spec?.max);
  }

  return defaultValue;
}

function maxTokensValidation(value: number | undefined, modelOption: LLMModelOption | undefined) {
  if (value === undefined || !hasBoundedParameterSpec(modelOption, 'max_tokens')) {
    return undefined;
  }

  const spec = parameterSpec(modelOption, 'max_tokens');

  if (!Number.isInteger(value)) {
    return 'Max tokens must be a whole number.';
  }

  if (!isInRange(value, spec?.min, spec?.max)) {
    if (spec?.min !== undefined && spec.max !== undefined) {
      return `Max tokens must be between ${spec.min} and ${spec.max}.`;
    }

    if (spec?.min !== undefined) {
      return `Max tokens must be at least ${spec.min}.`;
    }

    if (spec?.max !== undefined) {
      return `Max tokens must be at most ${spec.max}.`;
    }
  }

  return undefined;
}

function sanitizedValuesForSubmit(values: AgentFormValues, modelOption: LLMModelOption | undefined): AgentFormValues {
  const sanitizedValues = { ...values };

  if (!sanitizedValues.llm) {
    delete sanitizedValues.llmProvider;
    delete sanitizedValues.llmTemperature;
    delete sanitizedValues.llmMaxTokens;
    return sanitizedValues;
  }

  if (!modelOption) {
    delete sanitizedValues.llmTemperature;
    delete sanitizedValues.llmMaxTokens;
    return sanitizedValues;
  }

  if (!hasBoundedParameterSpec(modelOption, 'temperature')) {
    delete sanitizedValues.llmTemperature;
  } else if (sanitizedValues.llmTemperature !== undefined) {
    const spec = parameterSpec(modelOption, 'temperature');
    sanitizedValues.llmTemperature = clampNumber(sanitizedValues.llmTemperature, spec?.min, spec?.max);
  }

  if (!hasBoundedParameterSpec(modelOption, 'max_tokens')) {
    delete sanitizedValues.llmMaxTokens;
  }

  return sanitizedValues;
}

function cloneValues(values: AgentFormValues): AgentFormValues {
  return { ...values };
}

function cloneAttachments(attachments?: AgentAttachmentValues): AgentAttachmentValues {
  return {
    tools: [...(attachments?.tools ?? [])],
    toolConfigs: { ...(attachments?.toolConfigs ?? {}) },
    knowledgeSources: [...(attachments?.knowledgeSources ?? [])],
  };
}

export function AgentModal({
  open,
  mode,
  resetKey,
  initialValues,
  availableTools,
  availableKnowledgeSources,
  initialAttachments,
  llmModels,
  embedders,
  isSubmitting = false,
  onClose,
  onSubmit,
}: AgentModalProps) {
  const dialogRef = useRef<HTMLFormElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const previousOpenRef = useRef(false);
  const lastResetKeyRef = useRef<string | null>(null);
  const [values, setValues] = useState<AgentFormValues>(() => cloneValues(initialValues));
  const [attachments, setAttachments] = useState<AgentAttachmentValues>(() => cloneAttachments(initialAttachments));
  const llmModelLabels = useMemo(() => llmModels.map((model) => model.label), [llmModels]);
  const llmModelByLabel = useMemo(() => new Map(llmModels.map((model) => [model.label, model])), [llmModels]);
  const llmLabelByValue = useMemo(() => new Map(llmModels.map((model) => [model.value, model.label])), [llmModels]);
  const availableToolKeys = useMemo(() => availableTools.map((tool) => tool.tool_key), [availableTools]);
  const availableToolByKey = useMemo(() => toolByKey(availableTools), [availableTools]);
  const readyKnowledgeIds = useMemo(
    () => availableKnowledgeSources.filter((item) => item.status === 'ready').map((item) => item.id),
    [availableKnowledgeSources],
  );
  const knowledgeLabelById = useMemo(
    () => {
      const nameCounts = availableKnowledgeSources.reduce((counts, item) => {
        counts.set(item.name, (counts.get(item.name) ?? 0) + 1);
        return counts;
      }, new Map<string, number>());

      return new Map(
        availableKnowledgeSources.map((item) => [
          item.id,
          nameCounts.get(item.name) && nameCounts.get(item.name)! > 1
            ? `${item.name} · ${item.source_file_name || 'source'} · ${item.id.slice(0, 8)}`
            : item.name,
        ]),
      );
    },
    [availableKnowledgeSources],
  );
  const primaryModelOption = findModelOption(llmModels, values.llm);
  const primaryModelLabel = values.llm ? llmLabelByValue.get(values.llm) ?? values.llm : '';
  const functionCallingModelLabel = values.function_calling_llm
    ? llmLabelByValue.get(values.function_calling_llm) ?? values.function_calling_llm
    : '';
  const llmSelectLabels = useMemo(() => {
    const labels = new Set(llmModelLabels);

    if (values.llm && !llmLabelByValue.has(values.llm)) {
      labels.add(values.llm);
    }

    if (values.function_calling_llm && !llmLabelByValue.has(values.function_calling_llm)) {
      labels.add(values.function_calling_llm);
    }

    return [...labels];
  }, [llmLabelByValue, llmModelLabels, values.function_calling_llm, values.llm]);
  const temperatureSpec = parameterSpec(primaryModelOption, 'temperature');
  const maxTokensSpec = parameterSpec(primaryModelOption, 'max_tokens');
  const showTemperature = values.llm ? hasVisibleTemperatureControl(primaryModelOption, values.llmTemperature) : false;
  const showMaxTokens = values.llm ? hasBoundedParameterSpec(primaryModelOption, 'max_tokens') : false;
  const maxTokensError = maxTokensValidation(values.llmMaxTokens, primaryModelOption);

  useEffect(() => {
    const wasOpen = previousOpenRef.current;
    let focusTimer: number | undefined;

    if (open) {
      if (!wasOpen) {
        previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      }

      if (!wasOpen || lastResetKeyRef.current !== resetKey) {
        setValues(cloneValues(initialValues));
        setAttachments(cloneAttachments(initialAttachments));
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
  }, [open, resetKey]);

  if (!open) {
    return null;
  }

  function updateValue<K extends keyof AgentFormValues>(key: K, value: AgentFormValues[K]) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  function handlePrimaryLlmChange(label: string) {
    const selectedModel = label ? llmModelByLabel.get(label) : undefined;

    if (!label) {
      setValues((current) => ({
        ...current,
        llm: undefined,
        llmProvider: undefined,
        llmTemperature: undefined,
        llmMaxTokens: undefined,
      }));
      return;
    }

    setValues((current) => ({
      ...current,
      llm: selectedModel?.value ?? label,
      llmProvider: selectedModel ? inferProviderFromModelOption(llmModels, selectedModel.value) : current.llmProvider,
      llmTemperature: selectedModel
        ? normalizedParameterValue(current.llmTemperature, selectedModel, 'temperature')
        : current.llmTemperature,
      llmMaxTokens: selectedModel
        ? normalizedParameterValue(current.llmMaxTokens, selectedModel, 'max_tokens')
        : current.llmMaxTokens,
    }));
  }

  function handleFunctionCallingLlmChange(label: string) {
    const selectedModel = label ? llmModelByLabel.get(label) : undefined;

    setValues((current) => ({
      ...current,
      function_calling_llm: label ? selectedModel?.value ?? label : undefined,
      functionCallingLlmProvider: selectedModel
        ? inferProviderFromModelOption(llmModels, selectedModel.value)
        : label ? current.functionCallingLlmProvider : undefined,
    }));
  }

  function addAttachment(key: AttachmentListKey, item: string) {
    setAttachments((current) => {
      const currentItems = current[key] ?? [];

      if (currentItems.includes(item)) return current;
      if (key !== 'tools') {
        return { ...current, [key]: [...currentItems, item] };
      }
      const tool = availableToolByKey.get(item);
      return {
        ...current,
        tools: [...currentItems, item],
        toolConfigs: {
          ...(current.toolConfigs ?? {}),
          ...(tool ? { [item]: defaultToolConfig(tool) } : {}),
        },
      };
    });
  }

  function removeAttachment(key: AttachmentListKey, item: string) {
    setAttachments((current) => {
      const next = {
        ...current,
        [key]: (current[key] ?? []).filter((selectedItem) => selectedItem !== item),
      };
      if (key === 'tools') {
        const { [item]: _removed, ...remainingConfigs } = current.toolConfigs ?? {};
        next.toolConfigs = remainingConfigs;
      }
      return next;
    });
  }

  function updateToolConfig(toolKey: string, config: Record<string, unknown>) {
    setAttachments((current) => ({
      ...current,
      toolConfigs: {
        ...(current.toolConfigs ?? {}),
        [toolKey]: config,
      },
    }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (maxTokensError) {
      return;
    }
    const knowledgeSources = (attachments.knowledgeSources ?? [])
      .filter((id) => id.trim().length > 0);

    await onSubmit(sanitizedValuesForSubmit(values, primaryModelOption), {
      ...attachments,
      knowledgeSources,
    });
  }

  function handleKeyDown(event: KeyboardEvent<HTMLFormElement>) {
    if (event.key !== 'Escape') {
      return;
    }

    event.stopPropagation();
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-[#22170f]/50 backdrop-blur-sm" aria-hidden="true" />

      <form
        ref={dialogRef}
        role="dialog"
        aria-label="Configure Agent"
        aria-modal="true"
        tabIndex={-1}
        onSubmit={handleSubmit}
        onKeyDown={handleKeyDown}
        className="font-ax-body relative flex max-h-[85vh] w-full max-w-5xl flex-col overflow-hidden rounded-md border-2 border-[#7a5739] bg-[#fff6df] text-stone-900 shadow-[8px_8px_0_#7a5739]"
      >
        <div className="flex items-center justify-between gap-4 border-b-2 border-[#7a5739] bg-[#f8e8c8] px-6 py-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="rounded-md border-2 border-[#7a5739] bg-[#e6f6f2] p-2 shadow-[2px_2px_0_#7a5739]">
              <Bot aria-hidden="true" className="h-5 w-5 text-[#2f9b96]" />
            </div>
            <div className="min-w-0">
              <h2 className="text-lg font-black text-[#22170f]">Configure Agent</h2>
              <p className="font-ax-label m-0 text-xs font-medium uppercase tracking-wide text-stone-500">
                {mode === 'create' ? 'New agent' : 'Editing agent'}
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

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden md:flex-row">
          <div className="min-w-0 flex-1 space-y-6 overflow-y-auto p-6">
            <section className="space-y-4">
              <h3 className="font-ax-label flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-[#2f9b96]">
                <Sparkles aria-hidden="true" className="h-4 w-4 text-[#2f9b96]" />
                Identity & Role
              </h3>
              <FieldGroup label="Role">
                <TextInput
                  value={values.role}
                  onChange={(value) => updateValue('role', value)}
                  placeholder="Expert Analyst"
                />
              </FieldGroup>
              {/* [임시 추가] 에이전트 포토 공간 시연용 */}
              <FieldGroup label="Photo URL" helperText="Enter an image URL (e.g., /data/img/photo.png)">
                <TextInput
                  value={values.photo_url || ''}
                  onChange={(value) => updateValue('photo_url', value)}
                  placeholder="https://... or /data/img/..."
                />
              </FieldGroup>
              <FieldGroup label="Goal" helperText="What should this agent accomplish?">
                <TextInput
                  value={values.goal}
                  onChange={(value) => updateValue('goal', value)}
                  multiline
                  placeholder="Describe the objective..."
                />
              </FieldGroup>
              <FieldGroup label="Backstory">
                <TextInput
                  value={values.backstory}
                  onChange={(value) => updateValue('backstory', value)}
                  multiline
                  placeholder="Describe the agent's expertise and context..."
                />
              </FieldGroup>
            </section>

            <div className="grid gap-6 md:grid-cols-2">
              <section className="space-y-3">
                <h3 className="font-ax-label flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-stone-500">
                  <Wrench aria-hidden="true" className="h-4 w-4 text-[#2f9b96]" />
                  Agent Tools
                </h3>
                <MultiSelector
                  label="Tools"
                  options={availableToolKeys}
                  selected={attachments.tools ?? []}
                  onAdd={(value) => addAttachment('tools', value)}
                  onRemove={(value) => removeAttachment('tools', value)}
                  placeholder="Select a tool"
                />
                <ToolConfigPanel
                  tools={availableTools}
                  selectedToolKeys={attachments.tools ?? []}
                  toolConfigs={(attachments.toolConfigs ?? {}) as ToolConfigsByKey}
                  onChange={updateToolConfig}
                />
              </section>
              <section className="space-y-3">
                <h3 className="font-ax-label flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-stone-500">
                  <BookOpen aria-hidden="true" className="h-4 w-4 text-[#2f9b96]" />
                  Knowledge Sources
                </h3>
                <MultiSelector
                  label="Knowledge sources"
                  options={readyKnowledgeIds}
                  selected={attachments.knowledgeSources ?? []}
                  onAdd={(value) => addAttachment('knowledgeSources', value)}
                  onRemove={(value) => removeAttachment('knowledgeSources', value)}
                  getOptionLabel={(value) => knowledgeLabelById.get(value) ?? value}
                  placeholder="Select a source"
                />
              </section>
            </div>
          </div>

          <aside className="w-full shrink-0 overflow-y-auto border-t-2 border-[#7a5739] bg-[#f8e8c8]/70 md:w-[340px] md:border-l-2 md:border-t-0">
            <Section title="Runtime Behavior" icon={Zap}>
              <Toggle
                label="Verbose Logging"
                description="Show detailed execution logs"
                value={values.verbose}
                onChange={(value) => updateValue('verbose', value)}
              />
              <Toggle
                label="Allow Delegation"
                description="Agent can ask others for help"
                value={values.allow_delegation}
                onChange={(value) => updateValue('allow_delegation', value)}
              />
              <Toggle
                label="Reasoning"
                description="Enable reasoning controls"
                value={values.reasoning}
                onChange={(value) => updateValue('reasoning', value)}
              />
              {values.reasoning ? (
                <FieldGroup label="Max Reasoning Attempts" helperText="Maximum reasoning steps">
                  <NumberInput
                    value={values.max_reasoning_attempts}
                    onChange={(value) => updateValue('max_reasoning_attempts', value)}
                    placeholder="Default"
                  />
                </FieldGroup>
              ) : null}
            </Section>

            <Section title="Cost Optimization" icon={DollarSign} defaultOpen={false}>
              <div className="grid grid-cols-2 gap-3">
                <FieldGroup label="Max Iter" helperText="Default value is 25">
                  <NumberInput value={values.max_iter} onChange={(value) => updateValue('max_iter', value)} placeholder="25" />
                </FieldGroup>
                <FieldGroup label="Max RPM" helperText="Requests per minute">
                  <NumberInput value={values.max_rpm} onChange={(value) => updateValue('max_rpm', value)} placeholder="No limit" />
                </FieldGroup>
                <FieldGroup label="Retry Limit" helperText="Default value is 2">
                  <NumberInput
                    value={values.max_retry_limit}
                    onChange={(value) => updateValue('max_retry_limit', value)}
                    placeholder="2"
                  />
                </FieldGroup>
                <FieldGroup label="Execution Time" helperText="Limit in seconds">
                  <NumberInput
                    value={values.max_execution_time}
                    onChange={(value) => updateValue('max_execution_time', value)}
                    suffix="SEC"
                  />
                </FieldGroup>
              </div>
              <Toggle
                label="Context Window"
                description="Respect context window"
                value={values.respect_context_window}
                onChange={(value) => updateValue('respect_context_window', value)}
              />
              <Toggle
                label="Cache"
                description="Enable caching for this agent"
                value={values.cache}
                onChange={(value) => updateValue('cache', value)}
              />
            </Section>

            <Section title="Model Configuration" icon={Cpu} defaultOpen={false}>
              <SelectInput
                label="LLM"
                options={llmSelectLabels}
                value={primaryModelLabel}
                onChange={handlePrimaryLlmChange}
                placeholder="Default model"
              />
              {showTemperature ? (
                <SliderInput
                  label="Temperature"
                  value={values.llmTemperature}
                  min={temperatureSpec?.min ?? 0}
                  max={temperatureSpec?.max ?? 2}
                  step={0.1}
                  onChange={(value) => updateValue('llmTemperature', value)}
                />
              ) : null}
              {showMaxTokens ? (
                <FieldGroup label="Max tokens">
                  <NumberInput
                    value={values.llmMaxTokens}
                    onChange={(value) => updateValue('llmMaxTokens', value)}
                    placeholder={maxTokensSpec?.default?.toString() ?? 'Default'}
                  />
                  {maxTokensError ? (
                    <p className="m-0 text-xs font-medium text-rose-600">{maxTokensError}</p>
                  ) : null}
                </FieldGroup>
              ) : null}
              <SelectInput
                label="Function Calling LLM"
                options={llmSelectLabels}
                value={functionCallingModelLabel}
                onChange={handleFunctionCallingLlmChange}
                placeholder="Default model"
              />
              <SelectInput
                label="Embedder"
                options={embedders}
                value={values.embedder}
                onChange={(value) => updateValue('embedder', value)}
                placeholder="Default embedder"
              />
              <Toggle
                label="Multimodal"
                value={values.multimodal}
                onChange={(value) => updateValue('multimodal', value)}
              />
            </Section>

            <Section title="Date / Time Settings" icon={Clock} defaultOpen={false}>
              <Toggle
                label="Inject Date"
                value={values.inject_date}
                onChange={(value) => updateValue('inject_date', value)}
              />
              <FieldGroup label="Date Format">
                <TextInput
                  value={values.date_format}
                  onChange={(value) => updateValue('date_format', value)}
                  placeholder="%Y-%m-%d"
                />
              </FieldGroup>
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
              disabled={isSubmitting || !values.role.trim() || Boolean(maxTokensError)}
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
