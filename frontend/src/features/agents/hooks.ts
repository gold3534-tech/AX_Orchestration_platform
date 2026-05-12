import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { components } from '../../types/api.generated';
import { createAsset, deleteAsset, listAssets, updateAsset } from '../../api/assets';
import { listKnowledge, listVersionKnowledge, replaceVersionKnowledge } from '../../api/knowledge';
import { listTaskInputPresets, type TaskInputPresetCatalogItem } from '../../api/taskInputPresets';
import { attachTool, getToolCatalog, listAttachedTools } from '../../api/tooling';
import { queryKeys } from '../../hooks/queryKeys';
import type { KnowledgeItem, VersionKnowledgeBinding } from '../knowledge/knowledgeTypes';
import type { ToolConfigsByKey } from '../tools/toolConfig';
import { legacyModelString, legacyNumber, legacyProviderString } from './llmCatalog';

type AssetResponse = components['schemas']['AssetResponse'];
type ToolCatalogResponse = components['schemas']['ToolCatalogResponse'];
type VersionToolAttachmentReadResponse = components['schemas']['VersionToolAttachmentReadResponse'];

export type AgentKnowledgeSourceOption = Pick<KnowledgeItem, 'id' | 'name' | 'status' | 'source_file_name'>;

export type AgentListItem = {
  assetId: string;
  versionId: string;
  name: string;
  role: string;
  goal: string;
  backstory: string;
  photoUrl: string;
  allowDelegation: boolean;
  llm?: string;
  llmProvider?: string;
  llmTemperature?: number;
  llmMaxTokens?: number;
  function_calling_llm?: string;
  functionCallingLlmProvider?: string;
  max_iter?: number;
  max_rpm?: number;
  max_execution_time?: number;
  verbose?: boolean;
  allow_delegation?: boolean;
  reasoning?: boolean;
  max_reasoning_attempts?: number;
  cache?: boolean;
  respect_context_window?: boolean;
  max_retry_limit?: number;
  multimodal?: boolean;
  inject_date?: boolean;
  date_format?: string;
  embedder?: string;
  inputPresets?: string[];
  tools: string[];
  toolConfigs?: ToolConfigsByKey;
  knowledgeSources: string[];
  skills: string[];
  status: string;
};

export type AgentInputPresetOption = {
  key: string;
  label: string;
  inputType: string;
  description: string;
};

export type AgentFormValues = {
  role: string;
  goal: string;
  backstory: string;
  // [임시 추가] 에이전트 포토 공간 시연용
  photo_url?: string;
  llm?: string;
  llmProvider?: string;
  llmTemperature?: number;
  llmMaxTokens?: number;
  function_calling_llm?: string;
  functionCallingLlmProvider?: string;
  max_iter?: number;
  max_rpm?: number;
  max_execution_time?: number;
  verbose?: boolean;
  allow_delegation?: boolean;
  reasoning?: boolean;
  max_reasoning_attempts?: number;
  cache?: boolean;
  respect_context_window?: boolean;
  max_retry_limit?: number;
  multimodal?: boolean;
  inject_date?: boolean;
  date_format?: string;
  embedder?: string;
};

export type AgentAttachmentValues = {
  tools?: string[];
  toolConfigs?: ToolConfigsByKey;
  knowledgeSources?: string[];
};

export type CreateAgentInput = {
  values: AgentFormValues;
  attachments?: AgentAttachmentValues;
};

export type UpdateAgentInput = {
  assetId: string;
  baseVersionId: string;
  values: AgentFormValues;
  attachments?: AgentAttachmentValues;
  currentPayload?: Record<string, unknown>;
};

const agentAssetsQueryKey = [...queryKeys.assets.all(), 'agent'] as const;
const taskInputPresetsQueryKey = queryKeys.taskInputPresets.all();
const assetWriteAttachmentErrors = new WeakSet<object>();

type MutationResult<TData> = {
  data?: TData;
  error?: unknown;
};

function asString(value: unknown) {
  return typeof value === 'string' ? value : '';
}

function asOptionalString(value: unknown) {
  return typeof value === 'string' ? value : undefined;
}

function asOptionalNumber(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function asOptionalBoolean(value: unknown) {
  return typeof value === 'boolean' ? value : undefined;
}

function asStringArray(value: unknown) {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function asPayloadRecord(value: unknown) {
  return value !== null && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}

function toolConfigsFromAttachments(attachedTools: VersionToolAttachmentReadResponse[] = []): ToolConfigsByKey {
  return Object.fromEntries(attachedTools.map((tool) => [tool.tool_key, asPayloadRecord(tool.tool_config_json)]));
}

function asEmbedderModel(value: unknown) {
  if (typeof value === 'string') {
    return value;
  }

  return asOptionalString(asPayloadRecord(value).model);
}

function structuredLlmPayload(
  model: string | undefined,
  provider: string | undefined,
  options: { temperature?: number; maxTokens?: number } = {},
) {
  const selectedModel = model?.trim();

  if (!selectedModel || selectedModel === 'default') {
    return undefined;
  }

  return pickDefined({
    provider,
    model: selectedModel,
    temperature: options.temperature,
    max_tokens: options.maxTokens,
  });
}

function mapAssetToAgentListItem(
  asset: AssetResponse,
  attachedTools: VersionToolAttachmentReadResponse[] = [],
  boundKnowledge: VersionKnowledgeBinding[] = [],
): AgentListItem {
  const payload = asPayloadRecord(asset.current_version.payload);
  const inputPresets = asStringArray(payload.input_presets ?? payload.inputPresets);

  return {
    assetId: asset.id,
    versionId: asset.current_version.id,
    name: asset.name,
    role: asString(payload.role),
    goal: asString(payload.goal),
    backstory: asString(payload.backstory),
    photoUrl: asString(payload.photo_url),
    allowDelegation: Boolean(payload.allow_delegation),
    llm: legacyModelString(payload.llm),
    llmProvider: legacyProviderString(payload.llm),
    llmTemperature: legacyNumber(payload.llm, 'temperature'),
    llmMaxTokens: legacyNumber(payload.llm, 'max_tokens'),
    function_calling_llm: legacyModelString(payload.function_calling_llm),
    functionCallingLlmProvider: legacyProviderString(payload.function_calling_llm),
    max_iter: asOptionalNumber(payload.max_iter),
    max_rpm: asOptionalNumber(payload.max_rpm),
    max_execution_time: asOptionalNumber(payload.max_execution_time),
    verbose: asOptionalBoolean(payload.verbose),
    allow_delegation: asOptionalBoolean(payload.allow_delegation),
    reasoning: asOptionalBoolean(payload.reasoning),
    max_reasoning_attempts: asOptionalNumber(payload.max_reasoning_attempts),
    cache: asOptionalBoolean(payload.cache),
    respect_context_window: asOptionalBoolean(payload.respect_context_window),
    max_retry_limit: asOptionalNumber(payload.max_retry_limit),
    multimodal: asOptionalBoolean(payload.multimodal),
    inject_date: asOptionalBoolean(payload.inject_date),
    date_format: asOptionalString(payload.date_format),
    embedder: asEmbedderModel(payload.embedder),
    ...(inputPresets.length > 0 ? { inputPresets } : {}),
    tools: attachedTools.map((tool) => tool.tool_key),
    toolConfigs: toolConfigsFromAttachments(attachedTools),
    knowledgeSources: boundKnowledge.map((binding) => binding.knowledge_item_id),
    skills: asStringArray(payload.skills),
    status: asset.current_version.status,
  };
}

function mapTaskInputPresetCatalogItem(row: TaskInputPresetCatalogItem): AgentInputPresetOption {
  return {
    key: row.key,
    label: row.label,
    inputType: row.input_type,
    description: asString(row.description),
  };
}

function collectUniqueAgentsValues(agents: AgentListItem[], key: 'skills') {
  return [...new Set(agents.flatMap((agent) => agent[key]))];
}

export function agentDisplayName(values: Pick<AgentFormValues, 'role'>, fallback = 'Untitled Agent') {
  return values.role.trim() || fallback;
}

export function pickDefined<T extends Record<string, unknown>>(values: T) {
  return Object.fromEntries(
    Object.entries(values).filter(([, value]) => value !== undefined && value !== null && value !== ''),
  ) as Partial<T>;
}

export function toAgentAssetPayload(values: AgentFormValues) {
  const { embedder, ...payloadValues } = values;
  const llm = structuredLlmPayload(payloadValues.llm, payloadValues.llmProvider, {
    temperature: payloadValues.llmTemperature,
    maxTokens: payloadValues.llmMaxTokens,
  });
  const functionCallingLlm = structuredLlmPayload(
    payloadValues.function_calling_llm,
    payloadValues.functionCallingLlmProvider,
  );
  const payload = pickDefined({
    role: payloadValues.role,
    goal: payloadValues.goal,
    backstory: payloadValues.backstory,
    // [임시 추가] 에이전트 포토 공간 시연용
    photo_url: payloadValues.photo_url,
    llm,
    function_calling_llm: functionCallingLlm,
    max_iter: payloadValues.max_iter,
    max_rpm: payloadValues.max_rpm,
    max_execution_time: payloadValues.max_execution_time,
    verbose: payloadValues.verbose,
    allow_delegation: payloadValues.allow_delegation,
    reasoning: payloadValues.reasoning,
    max_reasoning_attempts: payloadValues.max_reasoning_attempts,
    cache: payloadValues.cache,
    respect_context_window: payloadValues.respect_context_window,
    max_retry_limit: payloadValues.max_retry_limit,
    multimodal: payloadValues.multimodal,
    inject_date: payloadValues.inject_date,
    date_format: payloadValues.date_format,
  });

  return embedder ? { ...payload, embedder: { model: embedder } } : payload;
}

export function mergeAgentAssetPayload(currentPayload: Record<string, unknown> | undefined, values: AgentFormValues) {
  const payload: Record<string, unknown> = { ...asPayloadRecord(currentPayload) };

  function setStringOrDelete(key: string, value: string | undefined) {
    if (value) {
      payload[key] = value;
    } else {
      delete payload[key];
    }
  }

  function setNumberOrDelete(key: string, value: number | undefined) {
    if (value !== undefined) {
      payload[key] = value;
    } else {
      delete payload[key];
    }
  }

  function setOptionalBoolean(key: string, value: boolean | undefined) {
    if (value !== undefined) {
      payload[key] = value;
    }
  }

  function setEmbedderOrDelete(value: string | undefined) {
    if (value) {
      payload.embedder = { model: value };
    } else {
      delete payload.embedder;
    }
  }

  function setLlmOrDelete(
    key: string,
    model: string | undefined,
    provider: string | undefined,
    options?: { temperature?: number; maxTokens?: number },
  ) {
    const llm = structuredLlmPayload(model, provider, options);

    if (llm) {
      payload[key] = llm;
    } else {
      delete payload[key];
    }
  }

  payload.role = values.role;
  payload.goal = values.goal;
  payload.backstory = values.backstory;
  // [임시 추가] 에이전트 포토 공간 시연용
  setStringOrDelete('photo_url', values.photo_url);
  setLlmOrDelete('llm', values.llm, values.llmProvider, {
    temperature: values.llmTemperature,
    maxTokens: values.llmMaxTokens,
  });
  setLlmOrDelete('function_calling_llm', values.function_calling_llm, values.functionCallingLlmProvider);
  setNumberOrDelete('max_iter', values.max_iter);
  setNumberOrDelete('max_rpm', values.max_rpm);
  setNumberOrDelete('max_execution_time', values.max_execution_time);
  setOptionalBoolean('verbose', values.verbose);
  setOptionalBoolean('allow_delegation', values.allow_delegation);
  setOptionalBoolean('reasoning', values.reasoning);
  setNumberOrDelete('max_reasoning_attempts', values.max_reasoning_attempts);
  setOptionalBoolean('cache', values.cache);
  setOptionalBoolean('respect_context_window', values.respect_context_window);
  setNumberOrDelete('max_retry_limit', values.max_retry_limit);
  setOptionalBoolean('multimodal', values.multimodal);
  setOptionalBoolean('inject_date', values.inject_date);
  setStringOrDelete('date_format', values.date_format);
  setEmbedderOrDelete(values.embedder);

  return payload;
}

function unwrapMutationResult<TData>({ data, error }: MutationResult<TData>) {
  if (error) {
    throw error;
  }

  return data;
}

function markAttachmentErrorAfterAssetWrite(error: unknown) {
  if ((typeof error === 'object' || typeof error === 'function') && error !== null) {
    assetWriteAttachmentErrors.add(error);
  }

  return error;
}

function didMutationWriteAsset(data: AssetResponse | undefined, error: unknown) {
  return Boolean(data?.id) || (
    (typeof error === 'object' || typeof error === 'function') &&
    error !== null &&
    assetWriteAttachmentErrors.has(error)
  );
}

async function attachSelectedTools(versionId: string, toolKeys: string[], toolConfigs: ToolConfigsByKey = {}) {
  await Promise.all(
    toolKeys.map(async (toolKey) => {
      unwrapMutationResult(
        await attachTool(versionId, {
          tool_key: toolKey,
          tool_config_json: asPayloadRecord(toolConfigs[toolKey]),
        }),
      );
    }),
  );
}

async function replaceSelectedKnowledge(versionId: string, knowledgeItemIds: string[] = []) {
  unwrapMutationResult(await replaceVersionKnowledge(versionId, knowledgeItemIds));
}

function normalizeCreateAgentInput(input: CreateAgentInput | AgentFormValues): CreateAgentInput {
  if ('values' in input) {
    return input;
  }

  const legacyValues = input as AgentFormValues & { tools?: string[] };

  return {
    values: legacyValues,
    attachments: { tools: legacyValues.tools ?? [] },
  };
}

export function useAgentsLibrary() {
  const agentsQuery = useQuery({
    queryKey: agentAssetsQueryKey,
    queryFn: async () => {
      const [assetsResult, catalogResult, knowledgeResult] = await Promise.all([
        listAssets('agent'),
        getToolCatalog(),
        listKnowledge(),
      ]);
      const agentAssets = unwrapMutationResult(assetsResult as MutationResult<AssetResponse[]>) ?? [];
      const toolCatalog = unwrapMutationResult(catalogResult as MutationResult<ToolCatalogResponse[]>) ?? [];
      const knowledgeSources = unwrapMutationResult(knowledgeResult as MutationResult<KnowledgeItem[]>) ?? [];

      const attachmentResults = await Promise.all(
        agentAssets.map(async (asset) => {
          const [attachedToolsResult, boundKnowledgeResult] = await Promise.all([
            listAttachedTools(asset.current_version.id),
            listVersionKnowledge(asset.current_version.id),
          ]);
          const attachedTools = unwrapMutationResult(
            attachedToolsResult as MutationResult<VersionToolAttachmentReadResponse[]>,
          ) ?? [];
          const boundKnowledge = unwrapMutationResult(
            boundKnowledgeResult as MutationResult<VersionKnowledgeBinding[]>,
          ) ?? [];

          return [asset.current_version.id, { attachedTools, boundKnowledge }] as const;
        }),
      );
      const attachmentsByVersionId = new Map(attachmentResults);

      return {
        agents: agentAssets.map((asset) => {
          const attachments = attachmentsByVersionId.get(asset.current_version.id);

          return mapAssetToAgentListItem(asset, attachments?.attachedTools, attachments?.boundKnowledge);
        }),
        agentPayloadsByAssetId: new Map(agentAssets.map((asset) => [asset.id, asPayloadRecord(asset.current_version.payload)])),
        tools: toolCatalog.map((tool) => tool.tool_key),
        toolCatalog,
        knowledgeSources,
      };
    },
  });

  const presetsQuery = useQuery({
    queryKey: taskInputPresetsQueryKey,
    queryFn: async () => (await listTaskInputPresets()).map(mapTaskInputPresetCatalogItem),
  });

  const agents = agentsQuery.data?.agents ?? [];

  return {
    agents,
    agentPayloadsByAssetId: agentsQuery.data?.agentPayloadsByAssetId ?? new Map<string, Record<string, unknown>>(),
    inputPresets: presetsQuery.data ?? [],
    tools: agentsQuery.data?.tools ?? [],
    toolCatalog: agentsQuery.data?.toolCatalog ?? [],
    knowledgeSources: agentsQuery.data?.knowledgeSources ?? [],
    skills: collectUniqueAgentsValues(agents, 'skills'),
    isLoading: agentsQuery.isLoading,
    isError: agentsQuery.isError,
    error: agentsQuery.error,
    refetch: agentsQuery.refetch,
    presetCatalogError: presetsQuery.error,
    isPresetCatalogLoading: presetsQuery.isLoading,
    refetchPresetCatalog: presetsQuery.refetch,
  };
}

export function useCreateAgent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: CreateAgentInput | AgentFormValues) => {
      const { values, attachments } = normalizeCreateAgentInput(input);
      const created = unwrapMutationResult(
        await createAsset({
          type: 'agent',
          name: agentDisplayName(values),
          description: values.role,
          payload: toAgentAssetPayload(values),
        }),
      );

      if (created?.current_version?.id) {
        try {
          await attachSelectedTools(created.current_version.id, attachments?.tools ?? [], attachments?.toolConfigs ?? {});
          await replaceSelectedKnowledge(created.current_version.id, attachments?.knowledgeSources ?? []);
        } catch (error) {
          throw markAttachmentErrorAfterAssetWrite(error);
        }
      }

      return created;
    },
    onSettled: async (data, error) => {
      if (didMutationWriteAsset(data, error)) {
        await queryClient.invalidateQueries({ queryKey: agentAssetsQueryKey });
        await queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.all() });
      }
    },
  });
}

export function useUpdateAgent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ assetId, baseVersionId, values, attachments, currentPayload }: UpdateAgentInput) => {
      const updated = unwrapMutationResult(
        await updateAsset(assetId, {
          base_version_id: baseVersionId,
          name: agentDisplayName(values),
          description: values.role,
          payload: mergeAgentAssetPayload(currentPayload, values),
        }),
      );

      if (updated?.current_version?.id) {
        try {
          await attachSelectedTools(updated.current_version.id, attachments?.tools ?? [], attachments?.toolConfigs ?? {});
          await replaceSelectedKnowledge(updated.current_version.id, attachments?.knowledgeSources ?? []);
        } catch (error) {
          throw markAttachmentErrorAfterAssetWrite(error);
        }
      }

      return updated;
    },
    onSettled: async (data, error) => {
      if (didMutationWriteAsset(data, error)) {
        await queryClient.invalidateQueries({ queryKey: agentAssetsQueryKey });
        await queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.all() });
      }
    },
  });
}

export function useDeleteAgent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (assetId: string) => unwrapMutationResult(await deleteAsset(assetId)),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: agentAssetsQueryKey });
    },
  });
}
