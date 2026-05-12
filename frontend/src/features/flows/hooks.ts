import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { components } from '../../types/api.generated';
import { createAsset, deleteAsset, listAssets, updateAsset } from '../../api/assets';
import {
  getFlowGraphDraft,
  listPublishedCrewsForFlow,
  publishFlowGraphDraft,
  runFlowCompatibilityDiagnostics,
  runFlowToolMockCallDiagnostics,
  saveFlowGraphDraft,
  validateFlowGraphDraft,
  type FlowGraphDocumentV1,
} from '../../api/flowGraphs';
import { queryKeys } from '../../hooks/queryKeys';
import type { FlowGraphNodeId, FlowNodeKind } from './flowGraphTypes';

type AssetResponse = components['schemas']['AssetResponse'];

export type FlowCanvasNodeDraft = {
  id: FlowGraphNodeId;
  type: FlowNodeKind;
  position: { x: number; y: number };
  data: Record<string, unknown>;
};

export type FlowCanvasEdgeDraft = {
  id: string;
  source: FlowGraphNodeId;
  target: FlowGraphNodeId;
  type: 'flow' | 'route' | 'tool_reference';
  data?: Record<string, unknown>;
};

export type FlowCanvasEntitiesDraft = NonNullable<FlowGraphDocumentV1['entities']>;
export type FlowCanvasViewportDraft = NonNullable<FlowGraphDocumentV1['viewport']>;

export type FlowCanvasDraft = {
  selectedNodeId: FlowGraphNodeId | null;
  layoutDirection?: string | null;
  viewport?: FlowCanvasViewportDraft | null;
  entities?: FlowCanvasEntitiesDraft;
  nodes: FlowCanvasNodeDraft[];
  edges: FlowCanvasEdgeDraft[];
};

export type FlowListItem = {
  assetId: string;
  versionId: string;
  versionNo: number;
  name: string;
  description: string;
  status: string;
};

export type PublishedCrewOption = {
  assetId: string;
  versionId: string;
  versionNo: number;
  name: string;
  description: string;
  status: string;
  runtimeSnapshot: Record<string, unknown>;
};

export type UpdateFlowInput = {
  assetId: string;
  baseVersionId: string;
  name: string;
  description: string;
  payload: Record<string, unknown>;
};

type MutationResult<TData> = {
  data?: TData;
  error?: unknown;
};

const flowAssetsQueryKey = [...queryKeys.assets.all(), 'flow'] as const;

function asString(value: unknown) {
  return typeof value === 'string' ? value : '';
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

function mapFlowAsset(asset: AssetResponse): FlowListItem {
  return {
    assetId: asset.id,
    versionId: asset.current_version.id,
    versionNo: asset.current_version.version_no,
    name: asset.name,
    description: asString(asset.description),
    status: asset.current_version.status,
  };
}

export function createEmptyFlowCanvasDraft(): FlowCanvasDraft {
  return {
    selectedNodeId: null,
    nodes: [],
    edges: [],
  };
}

export function useFlowLibrary() {
  const query = useQuery({
    queryKey: flowAssetsQueryKey,
    queryFn: async () => {
      const result = await listAssets('flow');
      const assets = unwrapQueryResult(result as MutationResult<AssetResponse[]>) ?? [];

      return {
        flows: assets.map(mapFlowAsset),
        flowAssetsById: new Map(assets.map((asset) => [asset.id, asset])),
      };
    },
  });

  return {
    flows: query.data?.flows ?? [],
    flowAssetsById: query.data?.flowAssetsById ?? new Map<string, AssetResponse>(),
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
}

export function usePublishedCrewsForFlow() {
  const query = useQuery({
    queryKey: queryKeys.flowGraphs.publishedCrews(),
    queryFn: async () =>
      (await listPublishedCrewsForFlow()).map(
        (crew): PublishedCrewOption => ({
          assetId: crew.asset_id,
          versionId: crew.version_id,
          versionNo: crew.version_no,
          name: crew.name,
          description: asString(crew.description),
          status: crew.status,
          runtimeSnapshot: crew.runtime_snapshot_json,
        }),
      ),
  });

  return {
    publishedCrews: query.data ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
}

export function useFlowDraft(flowAssetId?: string) {
  const query = useQuery({
    queryKey: flowAssetId
      ? queryKeys.flowGraphs.draft(flowAssetId)
      : ([...queryKeys.flowGraphs.all(), 'draft', 'unselected'] as const),
    queryFn: async () => (flowAssetId ? getFlowGraphDraft(flowAssetId) : null),
    enabled: Boolean(flowAssetId),
  });

  return {
    draft: query.data ?? null,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
}

export function useLoadFlowDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (flowAssetId: string) => getFlowGraphDraft(flowAssetId),
    onSuccess: (data, flowAssetId) => {
      queryClient.setQueryData(queryKeys.flowGraphs.draft(flowAssetId), data);
    },
  });
}

export function useSaveFlowDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ flowAssetId, graph }: { flowAssetId: string; graph: FlowGraphDocumentV1 }) =>
      saveFlowGraphDraft(flowAssetId, graph),
    onSuccess: async (_data, variables) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.flowGraphs.draft(variables.flowAssetId) });
    },
  });
}

export function useValidateFlowDraft() {
  return useMutation({
    mutationFn: async (flowAssetId: string) => validateFlowGraphDraft(flowAssetId),
  });
}

export function useFlowCompatibilityDiagnostics() {
  return useMutation({
    mutationFn: async ({ flowAssetId, inputs }: { flowAssetId: string; inputs?: Record<string, unknown> }) =>
      runFlowCompatibilityDiagnostics(flowAssetId, inputs ?? {}),
  });
}

export function useFlowToolMockCallDiagnostics() {
  return useMutation({
    mutationFn: async (flowAssetId: string) => runFlowToolMockCallDiagnostics(flowAssetId),
  });
}

export function usePublishFlowDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (flowAssetId: string) => publishFlowGraphDraft(flowAssetId),
    onSuccess: async (_data, flowAssetId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.flowGraphs.draft(flowAssetId) }),
        queryClient.invalidateQueries({ queryKey: flowAssetsQueryKey }),
        queryClient.invalidateQueries({ queryKey: queryKeys.assets.all() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.assets.detail(flowAssetId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.assets.versions(flowAssetId) }),
      ]);
    },
  });
}

export function useCreateFlow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ name, description }: { name: string; description: string }) =>
      unwrapMutationResult(
        await createAsset({
          type: 'flow',
          name,
          description,
          payload: {
            entry_method: 'run',
          },
        }),
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: flowAssetsQueryKey });
    },
  });
}

export function useUpdateFlow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ assetId, baseVersionId, name, description, payload }: UpdateFlowInput) =>
      unwrapMutationResult(
        await updateAsset(assetId, {
          base_version_id: baseVersionId,
          name,
          description,
          payload,
        }),
      ),
    onSuccess: async (_data, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: flowAssetsQueryKey }),
        queryClient.invalidateQueries({ queryKey: queryKeys.assets.all() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.assets.detail(variables.assetId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.assets.versions(variables.assetId) }),
      ]);
    },
  });
}

export function useDeleteFlow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (assetId: string) => {
      const result = await deleteAsset(assetId);
      if (result.error) {
        throw result.error;
      }
    },
    onSuccess: async (_data, assetId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: flowAssetsQueryKey }),
        queryClient.invalidateQueries({ queryKey: queryKeys.assets.all() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.assets.detail(assetId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.assets.versions(assetId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.flowGraphs.draft(assetId) }),
      ]);
    },
  });
}
