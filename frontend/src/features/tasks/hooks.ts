import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createAsset, deleteAsset, listAssets, updateAsset } from '../../api/assets';
import { listTaskInputPresets, type TaskInputPresetCatalogItem } from '../../api/taskInputPresets';
import { attachTool, getToolCatalog, listAttachedTools } from '../../api/tooling';
import { queryKeys } from '../../hooks/queryKeys';
import type { components } from '../../types/api.generated';
import type { ToolConfigsByKey } from '../tools/toolConfig';

type AssetResponse = components['schemas']['AssetResponse'];
type ToolCatalogResponse = components['schemas']['ToolCatalogResponse'];
type VersionToolAttachmentReadResponse = components['schemas']['VersionToolAttachmentReadResponse'];

export type TaskListItem = {
  assetId: string;
  versionId: string;
  name: string;
  description: string;
  expectedOutput: string;
  outputType: 'Raw' | 'Output JSON' | 'Output Pydantic';
  outputSchemaFields: OutputSchemaField[];
  asyncExecution?: boolean;
  humanInput?: boolean;
  markdown?: boolean;
  guardrailMaxRetries?: number;
  outputFile: string;
  createDirectory?: boolean;
  inputPresets: string[];
  tools: string[];
  toolConfigs: ToolConfigsByKey;
  summary: string;
  status: string;
};

export type TaskInputPresetOption = {
  key: string;
  label: string;
  inputType: string;
  description: string;
};

export type OutputSchemaField = {
  name: string;
  type: 'str' | 'int' | 'float' | 'bool' | 'dict' | 'list';
  description: string;
  required: boolean;
};

export type TaskFormValues = {
  name: string;
  description: string;
  expectedOutput: string;
  outputType?: 'Raw' | 'Output JSON' | 'Output Pydantic';
  outputSchemaFields?: OutputSchemaField[];
  asyncExecution?: boolean;
  humanInput?: boolean;
  markdown?: boolean;
  guardrailMaxRetries?: number;
  outputFile?: string;
  createDirectory?: boolean;
  inputPresets: string[];
  tools?: string[];
  toolConfigs?: ToolConfigsByKey;
};

export type UpdateTaskInput = {
  assetId: string;
  baseVersionId: string;
  values: TaskFormValues;
};

const taskAssetsQueryKey = [...queryKeys.assets.all(), 'task'] as const;
const taskInputPresetsQueryKey = queryKeys.taskInputPresets.all();
const assetWriteAttachmentErrors = new WeakSet<object>();
export const STRUCTURED_EXPECTED_OUTPUT_PLACEHOLDER = "A JSON object with 'title' and 'content' fields.";

type MutationResult<TData> = {
  data?: TData;
  error?: unknown;
};

function asString(value: unknown) {
  return typeof value === 'string' ? value : '';
}

function asStringArray(value: unknown) {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function asOptionalNumber(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function asOptionalBoolean(value: unknown) {
  return typeof value === 'boolean' ? value : undefined;
}

function asPayloadRecord(value: unknown) {
  return value !== null && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}

function asOutputType(value: unknown): NonNullable<TaskFormValues['outputType']> {
  if (value === 'Output JSON' || value === 'Output Pydantic') {
    return value;
  }

  return 'Raw';
}

export function asOutputSchemaFields(value: unknown): OutputSchemaField[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) => {
      const field = asPayloadRecord(item);
      const type = field.type;

      if (
        typeof field.name !== 'string' ||
        !['str', 'int', 'float', 'bool', 'dict', 'list'].includes(String(type))
      ) {
        return null;
      }

      return {
        name: field.name,
        type: type as OutputSchemaField['type'],
        description: typeof field.description === 'string' ? field.description : '',
        required: typeof field.required === 'boolean' ? field.required : true,
      };
    })
    .filter((field): field is OutputSchemaField => field !== null);
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

function mapAssetToTaskListItem(
  asset: AssetResponse,
  attachedTools: VersionToolAttachmentReadResponse[] = [],
): TaskListItem {
  const payload = asPayloadRecord(asset.current_version.payload);
  const description = asString(payload.description);
  const expectedOutput = asString(payload.expected_output);
  const inputPresets = asStringArray(payload.input_presets ?? payload.inputPresets);
  const outputType = asOutputType(payload.output_type);

  return {
    assetId: asset.id,
    versionId: asset.current_version.id,
    name: asset.name,
    description,
    expectedOutput,
    outputType,
    outputSchemaFields: outputType === 'Raw' ? [] : asOutputSchemaFields(payload.output_schema_fields),
    outputFile: asString(payload.output_file),
    ...pickDefined({
      asyncExecution: asOptionalBoolean(payload.async_execution),
      humanInput: asOptionalBoolean(payload.human_input),
      markdown: asOptionalBoolean(payload.markdown),
      guardrailMaxRetries: asOptionalNumber(payload.guardrail_max_retries),
      createDirectory: asOptionalBoolean(payload.create_directory),
    }),
    inputPresets,
    tools: attachedTools.map((tool) => tool.tool_key),
    toolConfigs: toolConfigsFromAttachments(attachedTools),
    summary: description || expectedOutput || asString(asset.description) || '설명이 아직 없습니다.',
    status: asset.current_version.status,
  };
}

function toolConfigsFromAttachments(attachedTools: VersionToolAttachmentReadResponse[] = []): ToolConfigsByKey {
  return Object.fromEntries(attachedTools.map((tool) => [tool.tool_key, asPayloadRecord(tool.tool_config_json)]));
}

function mapTaskInputPresetCatalogItem(row: TaskInputPresetCatalogItem): TaskInputPresetOption {
  return {
    key: row.key,
    label: row.label,
    inputType: row.input_type,
    description: asString(row.description),
  };
}

export function pickDefined<T extends Record<string, unknown>>(values: T) {
  return Object.fromEntries(
    Object.entries(values).filter(([, value]) => value !== undefined && value !== null && value !== ''),
  ) as Partial<T>;
}

export function structuredExpectedOutputFromFields(fields: OutputSchemaField[] = []) {
  const names = fields.map((field) => field.name.trim()).filter(Boolean);

  if (names.length === 0) {
    return STRUCTURED_EXPECTED_OUTPUT_PLACEHOLDER;
  }

  if (names.length === 1) {
    return `A JSON object with '${names[0]}' fields.`;
  }

  const quotedNames = names.map((name) => `'${name}'`);
  const fieldList = names.length === 2
    ? `${quotedNames[0]} and ${quotedNames[1]}`
    : `${quotedNames.slice(0, -1).join(', ')}, and ${quotedNames[quotedNames.length - 1]}`;

  return `A JSON object with ${fieldList} fields.`;
}

export function taskExpectedOutputForPayload(values: TaskFormValues) {
  if ((values.outputType ?? 'Raw') === 'Raw' || values.expectedOutput.trim().length > 0) {
    return values.expectedOutput;
  }

  return structuredExpectedOutputFromFields(values.outputSchemaFields);
}

export function toTaskAssetPayload(values: TaskFormValues) {
  const outputType = values.outputType ?? 'Raw';
  const structuredOutput =
    outputType === 'Raw'
      ? {}
      : {
          output_type: outputType,
          output_schema_fields: values.outputSchemaFields ?? [],
        };

  return {
    description: values.description,
    expected_output: taskExpectedOutputForPayload(values),
    input_presets: values.inputPresets,
    ...pickDefined({
      ...structuredOutput,
      async_execution: values.asyncExecution,
      human_input: values.humanInput,
      markdown: values.markdown,
      guardrail_max_retries: values.guardrailMaxRetries,
      output_file: values.outputFile,
      create_directory: values.createDirectory,
    }),
  };
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

export function useTasksLibrary() {
  const tasksQuery = useQuery({
    queryKey: taskAssetsQueryKey,
    queryFn: async () => {
      const [assetsResult, catalogResult] = await Promise.all([listAssets('task'), getToolCatalog()]);
      const taskAssets = unwrapMutationResult(assetsResult as MutationResult<AssetResponse[]>) ?? [];
      const toolCatalog = unwrapMutationResult(catalogResult as MutationResult<ToolCatalogResponse[]>) ?? [];

      const attachmentResults = await Promise.all(
        taskAssets.map(async (asset) => {
          const attachedTools =
            unwrapMutationResult(
              await listAttachedTools(asset.current_version.id),
            ) ?? [];

          return [asset.current_version.id, attachedTools] as const;
        }),
      );
      const attachedToolsByVersionId = new Map(attachmentResults);

      return {
        tasks: taskAssets.map((asset) => mapAssetToTaskListItem(asset, attachedToolsByVersionId.get(asset.current_version.id))),
        tools: toolCatalog.map((tool) => tool.tool_key),
        toolCatalog,
      };
    },
  });

  const presetsQuery = useQuery({
    queryKey: taskInputPresetsQueryKey,
    queryFn: async () => (await listTaskInputPresets()).map(mapTaskInputPresetCatalogItem),
  });

  const tasks = tasksQuery.data?.tasks ?? [];

  return {
    tasks,
    inputPresets: presetsQuery.data ?? [],
    tools: tasksQuery.data?.tools ?? [],
    toolCatalog: tasksQuery.data?.toolCatalog ?? [],
    isLoading: tasksQuery.isLoading,
    isError: tasksQuery.isError,
    error: tasksQuery.error,
    refetch: tasksQuery.refetch,
    presetCatalogError: presetsQuery.error,
    isPresetCatalogLoading: presetsQuery.isLoading,
    refetchPresetCatalog: presetsQuery.refetch,
  };
}

export function useCreateTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (values: TaskFormValues) => {
      const created = unwrapMutationResult(
        await createAsset({
          type: 'task',
          name: values.name,
          description: values.description,
          payload: toTaskAssetPayload(values),
        }),
      );

      if (created?.current_version?.id) {
        try {
          await attachSelectedTools(created.current_version.id, values.tools ?? [], values.toolConfigs ?? {});
        } catch (error) {
          throw markAttachmentErrorAfterAssetWrite(error);
        }
      }

      return created;
    },
    onSettled: async (data, error) => {
      if (didMutationWriteAsset(data, error)) {
        await queryClient.invalidateQueries({ queryKey: taskAssetsQueryKey });
      }
    },
  });
}

export function useUpdateTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ assetId, baseVersionId, values }: UpdateTaskInput) => {
      const updated = unwrapMutationResult(
        await updateAsset(assetId, {
          base_version_id: baseVersionId,
          name: values.name,
          description: values.description,
          payload: toTaskAssetPayload(values),
        }),
      );

      if (updated?.current_version?.id) {
        try {
          await attachSelectedTools(updated.current_version.id, values.tools ?? [], values.toolConfigs ?? {});
        } catch (error) {
          throw markAttachmentErrorAfterAssetWrite(error);
        }
      }

      return updated;
    },
    onSettled: async (data, error) => {
      if (didMutationWriteAsset(data, error)) {
        await queryClient.invalidateQueries({ queryKey: taskAssetsQueryKey });
      }
    },
  });
}

export function useDeleteTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (assetId: string) => unwrapMutationResult(await deleteAsset(assetId)),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: taskAssetsQueryKey });
    },
  });
}
