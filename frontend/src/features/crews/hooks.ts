import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { components } from '../../types/api.generated';
import { createAsset, deleteAsset, listAssets, updateAsset } from '../../api/assets';
import type { CrewGraphDocumentV1 } from '../../api/crewGraphs';
import { getCrewGraphDraft, publishCrewGraphDraft, saveCrewGraphDraft, validateCrewGraphDraft } from '../../api/crewGraphs';
import { listVersionKnowledge } from '../../api/knowledge';
import { getToolCatalog, listAttachedTools } from '../../api/tooling';
import { queryKeys } from '../../hooks/queryKeys';
import { canvasDraftToGraphDocument } from './canvas/crewCanvasGraph';
import { createEmptyCrewCanvasDraft as createEmptyDirectCrewCanvasDraft } from './canvas/crewCanvasDraft';
import type { CrewCanvasDraft as DirectCrewCanvasDraft } from './canvas/crewCanvasTypes';
import type { CrewGraph } from './crewGraphTypes';

type AssetResponse = components['schemas']['AssetResponse'];
type ToolCatalogResponse = components['schemas']['ToolCatalogResponse'];
type VersionToolAttachmentReadResponse = components['schemas']['VersionToolAttachmentReadResponse'];
type VersionKnowledgeResponse = components['schemas']['VersionKnowledgeResponse'];

export type VersionToolAttachmentSummary = {
  tool_key: string;
  tool_config_json: Record<string, unknown>;
  sort_order: number;
};

export type VersionKnowledgeAttachmentSummary = {
  knowledge_item_id: string;
  knowledge: {
    id: string;
    name: string;
    status: string;
    source_file_name?: string | null;
  };
  sort_order: number;
};

export type CrewLibraryOption = {
  assetId: string;
  versionId: string;
  name: string;
  subtitle: string;
  toolKeys: string[];
};

export type CrewToolOption = {
  key: string;
  name: string;
  description: string;
};

export type CrewCanvasDraft = DirectCrewCanvasDraft;

export type CrewGraphEntity = {
  asset_id: string;
  version_id: string;
  version_no: number;
  name: string;
  description?: string | null;
  status: string;
  payload: Record<string, unknown>;
};

export type CrewGraphToolEntity = {
  tool_key: string;
  name: string;
  description: string;
  tool_type: string;
  module_path: string;
  class_name: string;
  default_config_json: Record<string, unknown>;
  config_schema_json?: Record<string, unknown>;
  input_schema_json?: Record<string, unknown>;
  ui_schema_json?: Record<string, unknown>;
  required_env_vars?: Record<string, unknown>[];
  credential_requirements?: components['schemas']['CredentialRequirement'][];
  attachments: Array<{
    version_id: string;
    tool_config_json: Record<string, unknown>;
    sort_order: number;
  }>;
};

export type CrewGraphKnowledgeEntity = {
  id: string;
  name: string;
  status: string;
  embedding_provider?: string;
  embedding_model?: string;
  attachments: Array<{
    version_id: string;
    sort_order: number;
  }>;
};

export type CrewGraphEntities = {
  agents: Record<string, CrewGraphEntity>;
  tasks: Record<string, CrewGraphEntity>;
  crews: Record<string, CrewGraphEntity>;
  tools: Record<string, CrewGraphToolEntity>;
  knowledge?: Record<string, CrewGraphKnowledgeEntity>;
};

export type CrewListItem = {
  assetId: string;
  versionId: string;
  versionNo: number;
  name: string;
  description: string;
  process: 'sequential' | 'hierarchical';
  processType: string;
  managerAgentAssetId: string;
  managerAgentName: string;
  managerLlm: string;
  managerLlmModel: string;
  functionCallingLlm: string;
  verbose: boolean;
  planning: boolean;
  memory: boolean;
  memoryEnabled: boolean;
  cache: boolean;
  maxRpm?: number;
  stream: boolean;
  tracing: boolean;
  checkpoint: boolean;
  outputLogFile: string;
  planningLlm: string;
  chatLlm: string;
  embedder: string;
  isVerbose: boolean;
  payload: Record<string, unknown>;
  status: string;
};

export type CrewFormValues = {
  name: string;
  description: string;
  process: 'sequential' | 'hierarchical';
  managerAgentAssetId: string;
  managerLlm: string;
  functionCallingLlm: string;
  verbose?: boolean;
  planning?: boolean;
  memory?: boolean;
  cache?: boolean;
  maxRpm?: number;
  stream?: boolean;
  tracing?: boolean;
  checkpoint?: boolean;
  outputLogFile: string;
  planningLlm: string;
  chatLlm: string;
  embedder: string;
  canvasDraft: CrewCanvasDraft;
};

export type UpdateCrewInput = {
  assetId: string;
  baseVersionId: string;
  values: CrewFormValues;
  currentPayload?: Record<string, unknown>;
};

export type SaveCrewDraftInput = {
  crewAssetId: string;
  graph: CrewGraphDocumentV1;
};

const crewAssetsQueryKey = [...queryKeys.assets.all(), 'crew'] as const;
export const DEFAULT_HIERARCHICAL_MANAGER_LLM = 'openai/gpt-4o-mini';

type MutationResult<TData> = {
  data?: TData;
  error?: unknown;
};

function asString(value: unknown) {
  return typeof value === 'string' ? value : '';
}

function asBoolean(value: unknown) {
  return typeof value === 'boolean' ? value : false;
}

function asOptionalBoolean(value: unknown) {
  return typeof value === 'boolean' ? value : undefined;
}

function asOptionalNumber(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function asPayloadRecord(value: unknown) {
  return value !== null && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}

function asProcess(value: unknown): 'sequential' | 'hierarchical' {
  return value === 'hierarchical' ? 'hierarchical' : 'sequential';
}

function asModel(value: unknown) {
  if (typeof value === 'string') {
    return value;
  }

  const record = asPayloadRecord(value);

  return asString(record.main_model) || asString(record.model);
}

function optionalPayloadBoolean(payload: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(payload, key)) {
      return asOptionalBoolean(payload[key]);
    }
  }

  return undefined;
}

function pickDefined<T extends Record<string, unknown>>(values: T) {
  return Object.fromEntries(
    Object.entries(values).filter(([, value]) => value !== undefined && value !== null && value !== ''),
  ) as Partial<T>;
}

function cleanModel(value: string) {
  return value.trim();
}

function managerLlmForProcess(process: CrewFormValues['process'], value: string) {
  const model = cleanModel(value);

  return process === 'hierarchical' && !model ? DEFAULT_HIERARCHICAL_MANAGER_LLM : model;
}

function unwrapMutationResult<TData>({ data, error }: MutationResult<TData>) {
  if (error) {
    throw error;
  }

  return data;
}

function unwrapQueryResult<TData>(result: MutationResult<TData>) {
  if (result.error) {
    throw result.error;
  }

  return result.data;
}

export function createEmptyCrewCanvasDraft(): CrewCanvasDraft {
  return createEmptyDirectCrewCanvasDraft();
}

export function toCrewAssetPayload(values: CrewFormValues) {
  const payload = pickDefined({
    process: values.process,
    manager_agent_asset_id: values.managerAgentAssetId,
    manager_llm: managerLlmForProcess(values.process, values.managerLlm),
    function_calling_llm: cleanModel(values.functionCallingLlm),
    verbose: values.verbose,
    planning: values.planning,
    memory: values.memory,
    cache: values.cache,
    max_rpm: values.maxRpm,
    stream: values.stream,
    tracing: values.tracing,
    checkpoint: values.checkpoint,
    output_log_file: values.outputLogFile,
    planning_llm: cleanModel(values.planningLlm),
    chat_llm: cleanModel(values.chatLlm),
  });

  const embedder = cleanModel(values.embedder);

  return embedder ? { ...payload, embedder: { model: embedder } } : payload;
}

export function mergeCrewAssetPayload(currentPayload: Record<string, unknown> | undefined, values: CrewFormValues) {
  const payload: Record<string, unknown> = { ...asPayloadRecord(currentPayload) };

  function setStringOrDelete(key: string, value: string) {
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

  function setModelOrDelete(key: string, value: string, wrapModel = false) {
    const model = cleanModel(value);

    if (!model) {
      delete payload[key];
      return;
    }

    const existingModel = asModel(payload[key]);
    if (existingModel === model && payload[key] && typeof payload[key] === 'object') {
      return;
    }

    payload[key] = wrapModel ? { model } : model;
  }

  function setOptionalBoolean(key: string, value: boolean | undefined) {
    if (value !== undefined) {
      payload[key] = value;
    }
  }

  payload.process = values.process;
  setStringOrDelete('manager_agent_asset_id', values.managerAgentAssetId);
  setModelOrDelete('manager_llm', managerLlmForProcess(values.process, values.managerLlm));
  setModelOrDelete('function_calling_llm', values.functionCallingLlm);
  setOptionalBoolean('verbose', values.verbose);
  setOptionalBoolean('planning', values.planning);
  setOptionalBoolean('memory', values.memory);
  setOptionalBoolean('cache', values.cache);
  setNumberOrDelete('max_rpm', values.maxRpm);
  setOptionalBoolean('stream', values.stream);
  setOptionalBoolean('tracing', values.tracing);
  setOptionalBoolean('checkpoint', values.checkpoint);
  setStringOrDelete('output_log_file', values.outputLogFile);
  setModelOrDelete('planning_llm', values.planningLlm);
  setModelOrDelete('chat_llm', values.chatLlm);
  setModelOrDelete('embedder', values.embedder, true);

  return payload;
}

function mapAssetToCrewListItem(asset: AssetResponse, agentsById: Map<string, CrewLibraryOption>): CrewListItem {
  const payload = asPayloadRecord(asset.current_version.payload);
  const managerAgentAssetId = asString(payload.manager_agent_asset_id);
  const process = asProcess(payload.process ?? payload.process_type);
  const managerLlm = asModel(payload.manager_llm ?? payload.manager_llm_config_json);
  const functionCallingLlm = asModel(payload.function_calling_llm ?? payload.function_calling_llm_config_json);
  const memory = asBoolean(payload.memory ?? payload.memory_enabled);
  const verbose = asBoolean(payload.verbose ?? payload.is_verbose);

  return {
    assetId: asset.id,
    versionId: asset.current_version.id,
    versionNo: asset.current_version.version_no,
    name: asset.name,
    description: asString(asset.description),
    process,
    processType: process,
    managerAgentAssetId,
    managerAgentName: managerAgentAssetId ? agentsById.get(managerAgentAssetId)?.name ?? 'Unknown agent' : '',
    managerLlm,
    managerLlmModel: managerLlm,
    functionCallingLlm,
    verbose,
    planning: asBoolean(payload.planning),
    memory,
    memoryEnabled: memory,
    cache: asBoolean(payload.cache),
    maxRpm: asOptionalNumber(payload.max_rpm),
    stream: asBoolean(payload.stream),
    tracing: asBoolean(payload.tracing),
    checkpoint: asBoolean(payload.checkpoint),
    outputLogFile: asString(payload.output_log_file),
    planningLlm: asModel(payload.planning_llm),
    chatLlm: asModel(payload.chat_llm),
    embedder: asModel(payload.embedder),
    isVerbose: verbose,
    payload,
    status: asset.current_version.status,
  };
}

function mapAssetToOption(asset: AssetResponse, subtitle: string): CrewLibraryOption {
  return {
    assetId: asset.id,
    versionId: asset.current_version.id,
    name: asset.name,
    subtitle,
    toolKeys: [],
  };
}

function mapToolCatalogEntryToOption(tool: ToolCatalogResponse): CrewToolOption {
  return {
    key: tool.tool_key,
    name: tool.name,
    description: tool.description,
  };
}

function mapAgentAssetToOption(asset: AssetResponse) {
  const payload = asPayloadRecord(asset.current_version.payload);
  return mapAssetToOption(asset, asString(payload.role) || asString(asset.description) || '역할 미정');
}

function mapTaskAssetToOption(asset: AssetResponse) {
  const payload = asPayloadRecord(asset.current_version.payload);
  return mapAssetToOption(asset, asString(payload.description) || asString(asset.description) || '설명 미정');
}

function toolKeysFromAttachments(attachedTools: VersionToolAttachmentReadResponse[] = []) {
  return attachedTools.map((tool) => tool.tool_key);
}

function toolAttachmentSummaries(attachedTools: VersionToolAttachmentReadResponse[] = []): VersionToolAttachmentSummary[] {
  return attachedTools.map((tool) => ({
    tool_key: tool.tool_key,
    tool_config_json: asPayloadRecord(tool.tool_config_json),
    sort_order: tool.sort_order,
  }));
}

function knowledgeAttachmentSummaries(boundKnowledge: VersionKnowledgeResponse[] = []): VersionKnowledgeAttachmentSummary[] {
  return boundKnowledge.map((binding) => ({
    knowledge_item_id: binding.knowledge_item_id,
    knowledge: {
      id: binding.knowledge.id,
      name: binding.knowledge.name,
      status: binding.knowledge.status,
      source_file_name: binding.knowledge.source_file_name,
    },
    sort_order: binding.sort_order,
  }));
}

export function createCrewFormValues(crew?: CrewListItem): CrewFormValues {
  const payload = asPayloadRecord(crew?.payload);

  return {
    name: crew?.name ?? '',
    description: crew?.description ?? '',
    process: crew?.process ?? asProcess(crew?.processType),
    managerAgentAssetId: crew?.managerAgentAssetId ?? '',
    managerLlm: crew?.managerLlm || crew?.managerLlmModel || asModel(payload.manager_llm ?? payload.manager_llm_config_json),
    functionCallingLlm: crew?.functionCallingLlm ?? '',
    verbose: optionalPayloadBoolean(payload, ['verbose', 'is_verbose']),
    planning: optionalPayloadBoolean(payload, ['planning']),
    memory: optionalPayloadBoolean(payload, ['memory', 'memory_enabled']),
    cache: optionalPayloadBoolean(payload, ['cache']),
    maxRpm: crew?.maxRpm,
    stream: optionalPayloadBoolean(payload, ['stream']),
    tracing: optionalPayloadBoolean(payload, ['tracing']),
    checkpoint: optionalPayloadBoolean(payload, ['checkpoint']),
    outputLogFile: crew?.outputLogFile ?? '',
    planningLlm: crew?.planningLlm ?? '',
    chatLlm: crew?.chatLlm ?? '',
    embedder: crew?.embedder ?? '',
    canvasDraft: createEmptyCrewCanvasDraft(),
  };
}

export function useCrewLibrary() {
  const query = useQuery({
    queryKey: crewAssetsQueryKey,
    queryFn: async () => {
      const [crewResult, agentsResult, tasksResult, toolsResult] = await Promise.all([
        listAssets('crew'),
        listAssets('agent'),
        listAssets('task'),
        getToolCatalog(),
      ]);

      const crewAssets = unwrapQueryResult(crewResult as MutationResult<AssetResponse[]>) ?? [];
      const agentAssets = unwrapQueryResult(agentsResult as MutationResult<AssetResponse[]>) ?? [];
      const taskAssets = unwrapQueryResult(tasksResult as MutationResult<AssetResponse[]>) ?? [];
      const toolCatalog = unwrapQueryResult(toolsResult as MutationResult<ToolCatalogResponse[]>) ?? [];

      const availableAgents = agentAssets.map(mapAgentAssetToOption);
      const availableTasks = taskAssets.map(mapTaskAssetToOption);
      const availableTools = toolCatalog.map(mapToolCatalogEntryToOption);
      const agentLookup = new Map(availableAgents.map((agent) => [agent.assetId, agent]));
      const crews = crewAssets.map((asset) => mapAssetToCrewListItem(asset, agentLookup));
      const crewAssetsById = new Map(crewAssets.map((asset) => [asset.id, asset]));
      const agentAssetsById = new Map(agentAssets.map((asset) => [asset.id, asset]));
      const taskAssetsById = new Map(taskAssets.map((asset) => [asset.id, asset]));
      const toolCatalogByKey = new Map(toolCatalog.map((tool) => [tool.tool_key, tool]));
      const [agentAttachmentEntries, taskAttachmentEntries] = await Promise.all([
        Promise.all(
          agentAssets.map(async (asset) => {
            const [attachedTools, boundKnowledge] = await Promise.all([
              listAttachedTools(asset.current_version.id),
              listVersionKnowledge(asset.current_version.id),
            ]);
            const attachedToolRows = unwrapQueryResult(attachedTools as MutationResult<VersionToolAttachmentReadResponse[]>) ?? [];
            const boundKnowledgeRows = unwrapQueryResult(boundKnowledge as MutationResult<VersionKnowledgeResponse[]>) ?? [];
            return [
              asset.current_version.id,
              {
                keys: toolKeysFromAttachments(attachedToolRows),
                attachments: toolAttachmentSummaries(attachedToolRows),
                knowledgeAttachments: knowledgeAttachmentSummaries(boundKnowledgeRows),
              },
            ] as const;
          }),
        ),
        Promise.all(
          taskAssets.map(async (asset) => {
            const attachedTools = unwrapQueryResult(
              await listAttachedTools(asset.current_version.id),
            ) ?? [];
            return [
              asset.current_version.id,
              {
                keys: toolKeysFromAttachments(attachedTools),
                attachments: toolAttachmentSummaries(attachedTools),
              },
            ] as const;
          }),
        ),
      ]);
      const agentVersionTools = new Map(agentAttachmentEntries.map(([versionId, value]) => [versionId, value.keys]));
      const taskVersionTools = new Map(taskAttachmentEntries.map(([versionId, value]) => [versionId, value.keys]));
      const agentVersionToolAttachments = new Map(
        agentAttachmentEntries.map(([versionId, value]) => [versionId, value.attachments]),
      );
      const agentVersionKnowledgeAttachments = new Map(
        agentAttachmentEntries.map(([versionId, value]) => [versionId, value.knowledgeAttachments]),
      );
      const taskVersionToolAttachments = new Map(
        taskAttachmentEntries.map(([versionId, value]) => [versionId, value.attachments]),
      );
      const agentsWithTools = availableAgents.map((agent) => ({
        ...agent,
        toolKeys: agentVersionTools.get(agent.versionId) ?? [],
      }));
      const tasksWithTools = availableTasks.map((task) => ({
        ...task,
        toolKeys: taskVersionTools.get(task.versionId) ?? [],
      }));

      return {
        crews,
        availableAgents: agentsWithTools,
        availableTasks: tasksWithTools,
        availableTools,
        crewAssetsById,
        agentAssetsById,
        taskAssetsById,
        toolCatalogByKey,
        agentVersionTools,
        taskVersionTools,
        agentVersionToolAttachments,
        agentVersionKnowledgeAttachments,
        taskVersionToolAttachments,
      };
    },
  });

  return {
    crews: query.data?.crews ?? [],
    availableAgents: query.data?.availableAgents ?? [],
    availableTasks: query.data?.availableTasks ?? [],
    availableTools: query.data?.availableTools ?? [],
    crewAssetsById: query.data?.crewAssetsById ?? new Map<string, AssetResponse>(),
    agentAssetsById: query.data?.agentAssetsById ?? new Map<string, AssetResponse>(),
    taskAssetsById: query.data?.taskAssetsById ?? new Map<string, AssetResponse>(),
    toolCatalogByKey: query.data?.toolCatalogByKey ?? new Map<string, ToolCatalogResponse>(),
    agentVersionTools: query.data?.agentVersionTools ?? new Map<string, string[]>(),
    taskVersionTools: query.data?.taskVersionTools ?? new Map<string, string[]>(),
    agentVersionToolAttachments: query.data?.agentVersionToolAttachments ?? new Map<string, VersionToolAttachmentSummary[]>(),
    agentVersionKnowledgeAttachments: query.data?.agentVersionKnowledgeAttachments ?? new Map<string, VersionKnowledgeAttachmentSummary[]>(),
    taskVersionToolAttachments: query.data?.taskVersionToolAttachments ?? new Map<string, VersionToolAttachmentSummary[]>(),
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
}

function unique<T>(values: T[]) {
  return Array.from(new Set(values));
}

export function validateCrewDraftReferences(args: {
  draft: CrewCanvasDraft;
  agentAssetsById: Map<string, unknown>;
  taskAssetsById: Map<string, unknown>;
}) {
  const { draft, agentAssetsById, taskAssetsById } = args;

  for (const node of draft.nodes) {
    if (node.kind === 'agent' && !agentAssetsById.has(node.assetId)) {
      return `Agent node references an unknown Agent. Rebind or remove ${node.nodeId}.`;
    }
    if (node.kind === 'task' && !taskAssetsById.has(node.assetId)) {
      return `Task node references an unknown Task. Rebind or remove ${node.nodeId}.`;
    }
  }

  return '';
}

export function buildCrewGraphDocument(args: {
  crewAsset: AssetResponse;
  draft: CrewCanvasDraft;
  agentAssetsById: Map<string, AssetResponse>;
  taskAssetsById: Map<string, AssetResponse>;
  toolCatalogByKey: Map<string, ToolCatalogResponse>;
  agentVersionTools?: Map<string, string[]>;
  taskVersionTools?: Map<string, string[]>;
  agentVersionToolAttachments?: Map<string, VersionToolAttachmentSummary[]>;
  agentVersionKnowledgeAttachments?: Map<string, VersionKnowledgeAttachmentSummary[]>;
  taskVersionToolAttachments?: Map<string, VersionToolAttachmentSummary[]>;
}): CrewGraphDocumentV1 & { entities: CrewGraphEntities } {
  return canvasDraftToGraphDocument({
    ...args,
    draft: args.draft,
  });
}

export function useCreateCrew() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (values: CrewFormValues) =>
      unwrapMutationResult(
        await createAsset({
          type: 'crew',
          name: values.name,
          description: values.description,
          payload: toCrewAssetPayload(values),
        }),
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: crewAssetsQueryKey });
    },
  });
}

export function useUpdateCrew() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ assetId, baseVersionId, values, currentPayload }: UpdateCrewInput) =>
      unwrapMutationResult(
        await updateAsset(assetId, {
          base_version_id: baseVersionId,
          name: values.name,
          description: values.description,
          payload: mergeCrewAssetPayload(currentPayload, values),
        }),
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: crewAssetsQueryKey });
    },
  });
}

export function useDeleteCrew() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (assetId: string) => unwrapMutationResult(await deleteAsset(assetId)),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: crewAssetsQueryKey });
    },
  });
}

export function useSaveCrewDraft() {
  return useMutation({
    mutationFn: async ({ crewAssetId, graph }: SaveCrewDraftInput) => saveCrewGraphDraft(crewAssetId, graph),
  });
}

export function useLoadCrewDraft() {
  return useMutation({
    mutationFn: async (crewAssetId: string) => getCrewGraphDraft(crewAssetId),
  });
}

export function useValidateCrewDraft() {
  return useMutation({
    mutationFn: async (crewAssetId: string) => validateCrewGraphDraft(crewAssetId),
  });
}

export function usePublishCrewDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (crewAssetId: string) => publishCrewGraphDraft(crewAssetId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: crewAssetsQueryKey });
    },
  });
}
