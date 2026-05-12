import type {
  CrewCanvasAgentNodeDraft,
  CrewCanvasAgentNodeId,
  CrewCanvasDraft,
  CrewCanvasEdgeDraft,
  CrewCanvasNodeId,
  CrewCanvasNodeSize,
  CrewCanvasPlaceholderNodeId,
  CrewCanvasTaskNodeDraft,
  CrewCanvasTaskNodeId,
} from './crewCanvasTypes';
import type { XYPosition } from '@xyflow/react';

type CrewCanvasNodeBinding =
  | {
      kind: 'agent';
      assetId: string;
      versionId: string;
    }
  | {
      kind: 'task';
      assetId: string;
      versionId: string;
    };

export function createEmptyCrewCanvasDraft(): CrewCanvasDraft {
  return {
    selectedNodeId: null,
    nodes: [],
    edges: [],
    insertionOrder: [],
    nodePositions: {},
    nodeSizes: {},
  };
}

export function addPlaceholderNode(
  draft: CrewCanvasDraft,
  { nodeId, position }: { nodeId: CrewCanvasPlaceholderNodeId; position?: XYPosition },
): CrewCanvasDraft {
  if (draft.nodes.some((node) => node.nodeId === nodeId)) return draft;

  const node = {
    nodeId,
    kind: 'placeholder',
    insertedAt: nextInsertedAt(draft),
  } as const;

  return {
    ...draft,
    nodes: [...draft.nodes, node],
    insertionOrder: [...draft.insertionOrder, nodeId],
    nodePositions: position ? { ...draft.nodePositions, [nodeId]: position } : draft.nodePositions,
  };
}

export function bindCanvasNode(draft: CrewCanvasDraft, nodeId: CrewCanvasNodeId, binding: CrewCanvasNodeBinding): CrewCanvasDraft {
  const oldNode = draft.nodes.find((node) => node.nodeId === nodeId);
  const insertedAt = oldNode?.insertedAt ?? nextInsertedAt(draft);
  const nextNode = toBoundNode(binding, insertedAt);
  const nextPosition = draft.nodePositions[nodeId] ?? draft.nodePositions[nextNode.nodeId];
  const nextSize = draft.nodeSizes?.[nodeId] ?? draft.nodeSizes?.[nextNode.nodeId];
  const nodesWithoutDuplicate = draft.nodes.filter((node) => node.nodeId === nodeId || node.nodeId !== nextNode.nodeId);
  const hasNextNode = draft.nodes.some((node) => node.nodeId === nextNode.nodeId);
  const nextNodes = oldNode
    ? nodesWithoutDuplicate.map((node) => (node.nodeId === nodeId ? nextNode : node))
    : hasNextNode
      ? draft.nodes.map((node) => (node.nodeId === nextNode.nodeId ? nextNode : node))
      : [...draft.nodes, nextNode];

  const nodePositions = removeNodePosition(removeNodePosition(draft.nodePositions, nodeId), nextNode.nodeId);
  const nextNodePositions = nextPosition ? { ...nodePositions, [nextNode.nodeId]: nextPosition } : nodePositions;
  const nodeSizes = removeNodeSize(removeNodeSize(draft.nodeSizes ?? {}, nodeId), nextNode.nodeId);
  const nextNodeSizes = nextSize ? { ...nodeSizes, [nextNode.nodeId]: nextSize } : nodeSizes;

  return {
    ...draft,
    selectedNodeId: draft.selectedNodeId === nodeId ? nextNode.nodeId : draft.selectedNodeId,
    nodes: nextNodes,
    edges: nodeId === nextNode.nodeId ? draft.edges : draft.edges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId),
    insertionOrder: replaceOrAppend(draft.insertionOrder, nodeId, nextNode.nodeId),
    nodePositions: nextNodePositions,
    nodeSizes: nextNodeSizes,
  };
}

export function deleteCanvasNode(draft: CrewCanvasDraft, nodeId: CrewCanvasNodeId): CrewCanvasDraft {
  return {
    ...draft,
    selectedNodeId: draft.selectedNodeId === nodeId ? null : draft.selectedNodeId,
    nodes: draft.nodes.filter((node) => node.nodeId !== nodeId),
    edges: draft.edges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId),
    insertionOrder: draft.insertionOrder.filter((id) => id !== nodeId),
    nodePositions: removeNodePosition(draft.nodePositions, nodeId),
    nodeSizes: removeNodeSize(draft.nodeSizes ?? {}, nodeId),
  };
}

export function deleteCanvasEdge(draft: CrewCanvasDraft, edgeId: string): CrewCanvasDraft {
  return {
    ...draft,
    edges: draft.edges.filter((edge) => edge.id !== edgeId),
  };
}

export function upsertCanvasEdge(draft: CrewCanvasDraft, edge: CrewCanvasEdgeDraft): CrewCanvasDraft {
  const edgeIndex = draft.edges.findIndex((currentEdge) => currentEdge.id === edge.id);
  if (edgeIndex === -1) {
    return {
      ...draft,
      edges: [...draft.edges, edge],
    };
  }

  return {
    ...draft,
    edges: draft.edges.map((currentEdge, index) => (index === edgeIndex ? edge : currentEdge)),
  };
}

export function commitCanvasNodePosition(draft: CrewCanvasDraft, nodeId: CrewCanvasNodeId, position: XYPosition): CrewCanvasDraft {
  return {
    ...draft,
    nodePositions: {
      ...draft.nodePositions,
      [nodeId]: position,
    },
  };
}

export function commitCanvasNodeSize(draft: CrewCanvasDraft, nodeId: CrewCanvasNodeId, size: CrewCanvasNodeSize): CrewCanvasDraft {
  if (!isValidNodeSize(size)) return draft;

  return {
    ...draft,
    nodeSizes: {
      ...(draft.nodeSizes ?? {}),
      [nodeId]: size,
    },
  };
}

function nextInsertedAt(draft: CrewCanvasDraft) {
  return draft.nodes.reduce((maxInsertedAt, node) => Math.max(maxInsertedAt, node.insertedAt), -1) + 1;
}

function toBoundNode(binding: CrewCanvasNodeBinding, insertedAt: number): CrewCanvasAgentNodeDraft | CrewCanvasTaskNodeDraft {
  if (binding.kind === 'agent') {
    return {
      nodeId: `agent:${binding.assetId}` as CrewCanvasAgentNodeId,
      kind: 'agent',
      assetId: binding.assetId,
      versionId: binding.versionId,
      insertedAt,
    };
  }

  return {
    nodeId: `task:${binding.assetId}` as CrewCanvasTaskNodeId,
    kind: 'task',
    assetId: binding.assetId,
    versionId: binding.versionId,
    insertedAt,
  };
}

function replaceOrAppend(values: readonly CrewCanvasNodeId[], oldValue: CrewCanvasNodeId, newValue: CrewCanvasNodeId) {
  if (values.includes(newValue) && oldValue !== newValue) {
    return values.filter((value) => value !== oldValue);
  }
  if (values.includes(oldValue)) {
    return values.map((value) => (value === oldValue ? newValue : value));
  }
  return [...values, newValue];
}

function removeNodePosition(nodePositions: CrewCanvasDraft['nodePositions'], nodeId: CrewCanvasNodeId) {
  const { [nodeId]: _removedPosition, ...rest } = nodePositions;
  return rest;
}

function removeNodeSize(nodeSizes: NonNullable<CrewCanvasDraft['nodeSizes']>, nodeId: CrewCanvasNodeId) {
  const { [nodeId]: _removedSize, ...rest } = nodeSizes;
  return rest;
}

function isValidNodeSize(size: CrewCanvasNodeSize) {
  return Number.isFinite(size.width) && Number.isFinite(size.height) && size.width > 0 && size.height > 0;
}

type LatestVersionAssetLike = {
  current_version?: {
    id?: string | null;
  } | null;
};

export type CrewCanvasStaleNodeReference = {
  nodeId: CrewCanvasNodeId;
  kind: 'agent' | 'task';
  assetId: string;
  currentVersionId: string;
  latestVersionId: string;
};

export function findStaleCanvasNodeReferences(args: {
  draft: CrewCanvasDraft;
  agentAssetsById: Map<string, LatestVersionAssetLike>;
  taskAssetsById: Map<string, LatestVersionAssetLike>;
}): CrewCanvasStaleNodeReference[] {
  const { draft, agentAssetsById, taskAssetsById } = args;
  const staleReferences: CrewCanvasStaleNodeReference[] = [];

  for (const node of draft.nodes) {
    if (node.kind === 'agent') {
      const latestVersionId = currentVersionIdForAsset(agentAssetsById.get(node.assetId));
      if (latestVersionId && latestVersionId !== node.versionId) {
        staleReferences.push({
          nodeId: node.nodeId,
          kind: 'agent',
          assetId: node.assetId,
          currentVersionId: node.versionId,
          latestVersionId,
        });
      }
    }

    if (node.kind === 'task') {
      const latestVersionId = currentVersionIdForAsset(taskAssetsById.get(node.assetId));
      if (latestVersionId && latestVersionId !== node.versionId) {
        staleReferences.push({
          nodeId: node.nodeId,
          kind: 'task',
          assetId: node.assetId,
          currentVersionId: node.versionId,
          latestVersionId,
        });
      }
    }
  }

  return staleReferences;
}

export function rebindStaleCanvasNodeReferences(args: {
  draft: CrewCanvasDraft;
  agentAssetsById: Map<string, LatestVersionAssetLike>;
  taskAssetsById: Map<string, LatestVersionAssetLike>;
}): CrewCanvasDraft {
  const staleReferences = findStaleCanvasNodeReferences(args);
  if (staleReferences.length === 0) return args.draft;

  const latestVersionIdByNodeId = new Map(staleReferences.map((reference) => [reference.nodeId, reference.latestVersionId]));
  return {
    ...args.draft,
    nodes: args.draft.nodes.map((node) => {
      if (node.kind === 'placeholder') return node;
      const latestVersionId = latestVersionIdByNodeId.get(node.nodeId);
      if (!latestVersionId) return node;
      return {
        ...node,
        versionId: latestVersionId,
      };
    }),
  };
}

function currentVersionIdForAsset(asset: LatestVersionAssetLike | undefined) {
  const id = asset?.current_version?.id;
  const trimmedId = typeof id === 'string' ? id.trim() : '';
  return trimmedId || '';
}
