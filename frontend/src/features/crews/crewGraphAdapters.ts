import { MarkerType } from '@xyflow/react';
import type { CrewGraphDocumentV1 } from '../../api/crewGraphs';
import type { CrewCanvasDraft, CrewLibraryOption, CrewToolOption } from './hooks';
import type {
  CrewCanvasEdgeDraft,
  CrewCanvasEdgeKind,
  CrewCanvasNodeDraft,
  CrewCanvasNodeId,
  CrewCanvasNodeSize,
} from './canvas/crewCanvasTypes';
import {
  AGENT_ASSIGNMENT_SOURCE_HANDLE,
  AGENT_ASSIGNMENT_TARGET_HANDLE,
  TASK_CONTEXT_SOURCE_HANDLE,
  TASK_CONTEXT_TARGET_HANDLE,
  TASK_SEQUENCE_SOURCE_HANDLE,
  TASK_SEQUENCE_TARGET_HANDLE,
} from './canvas/CrewCanvasNodes';
import type { CrewGraph, CrewGraphEdge, CrewGraphNode, CrewGraphNodeId } from './crewGraphTypes';
import { getDefaultCrewNodePosition, getDefaultPlaceholderNodePosition, toCrewNodeId } from './crewGraphTypes';

type GraphNodeLike = Omit<CrewGraphDocumentV1['nodes'][number], 'type'> & { type: string };
type GraphEdgeLike = Omit<CrewGraphDocumentV1['edges'][number], 'type'> & { type: string };

const EDGE_STYLES: Record<CrewCanvasEdgeKind, { color: string; label: string }> = {
  agent_assignment: { color: '#ef4444', label: 'Assign a agent' },
  task_context: { color: '#f97316', label: 'Context Transfer' },
  task_sequence: { color: '#22c55e', label: 'Task Sequence' },
};

const EDGE_HANDLES: Record<CrewCanvasEdgeKind, { sourceHandle: string; targetHandle: string }> = {
  agent_assignment: {
    sourceHandle: AGENT_ASSIGNMENT_SOURCE_HANDLE,
    targetHandle: AGENT_ASSIGNMENT_TARGET_HANDLE,
  },
  task_context: {
    sourceHandle: TASK_CONTEXT_SOURCE_HANDLE,
    targetHandle: TASK_CONTEXT_TARGET_HANDLE,
  },
  task_sequence: {
    sourceHandle: TASK_SEQUENCE_SOURCE_HANDLE,
    targetHandle: TASK_SEQUENCE_TARGET_HANDLE,
  },
};

const CREW_CONTAINER_DEFAULT_SIZE = { width: 1060, height: 520 };
const CREW_CONTAINER_MIN_SIZE = { width: 720, height: 360 };
const CREW_CONTAINER_CHILD_PADDING = { right: 80, bottom: 120 };
const CREW_CANVAS_NODE_SIZE_BY_KIND: Record<CrewCanvasNodeDraft['kind'], { width: number; height: number }> = {
  placeholder: { width: 220, height: 120 },
  agent: { width: 220, height: 160 },
  task: { width: 220, height: 160 },
};

function unique<T>(values: T[]) {
  return Array.from(new Set(values));
}

function nonEmptyString(value: unknown) {
  if (typeof value !== 'string') return '';
  const trimmed = value.trim();
  return trimmed ? trimmed : '';
}

function parsePrefixedId(prefix: string, value: string) {
  if (!value.startsWith(prefix)) return '';
  return value.slice(prefix.length);
}

function crewGraphNodeAssetId(node?: GraphNodeLike) {
  if (!node) return '';
  const assetId = nonEmptyString((node as any)?.data?.assetId);
  if (assetId) return assetId;

  if (node.type === 'agent') return parsePrefixedId('agent:', node.id);
  if (node.type === 'task') return parsePrefixedId('task:', node.id);
  return '';
}

function crewGraphNodeVersionId(node?: GraphNodeLike) {
  return nonEmptyString((node as any)?.data?.versionId);
}

function crewGraphNodeSize(node: GraphNodeLike): CrewCanvasNodeSize | null {
  const width = node.style?.width;
  const height = node.style?.height;
  if (
    typeof width !== 'number' ||
    typeof height !== 'number' ||
    !Number.isFinite(width) ||
    !Number.isFinite(height) ||
    width <= 0 ||
    height <= 0
  ) {
    return null;
  }
  return { width, height };
}

export function crewGraphDocumentToCanvasDraft(graph: CrewGraphDocumentV1): CrewCanvasDraft {
  const nodes = graph.nodes as GraphNodeLike[];
  const edges = graph.edges as GraphEdgeLike[];
  const draftNodes: CrewCanvasNodeDraft[] = nodes
    .map((node, index): CrewCanvasNodeDraft | null => {
      if (node.type === 'placeholder') {
        return {
          nodeId: node.id as CrewCanvasNodeId as Extract<CrewCanvasNodeDraft, { kind: 'placeholder' }>['nodeId'],
          kind: 'placeholder',
          insertedAt: index,
        };
      }

      if (node.type === 'agent') {
        const assetId = crewGraphNodeAssetId(node);
        const versionId = crewGraphNodeVersionId(node);
        if (!assetId || !versionId) return null;
        return {
          nodeId: node.id as CrewCanvasNodeId as Extract<CrewCanvasNodeDraft, { kind: 'agent' }>['nodeId'],
          kind: 'agent',
          assetId,
          versionId,
          insertedAt: index,
        };
      }

      if (node.type === 'task') {
        const assetId = crewGraphNodeAssetId(node);
        const versionId = crewGraphNodeVersionId(node);
        if (!assetId || !versionId) return null;
        return {
          nodeId: node.id as CrewCanvasNodeId as Extract<CrewCanvasNodeDraft, { kind: 'task' }>['nodeId'],
          kind: 'task',
          assetId,
          versionId,
          insertedAt: index,
        };
      }

      return null;
    })
    .filter((node): node is CrewCanvasNodeDraft => node !== null);
  const draftNodeIds = new Set<string>(draftNodes.map((node) => node.nodeId));
  const draftEdges: CrewCanvasEdgeDraft[] = edges
    .map((edge): CrewCanvasEdgeDraft | null => {
      if (!isEditableEdgeKind(edge.type)) return null;
      if (!draftNodeIds.has(edge.source as CrewCanvasNodeId) || !draftNodeIds.has(edge.target as CrewCanvasNodeId)) return null;
      return {
        id: edge.id,
        kind: edge.type,
        source: edge.source as CrewCanvasNodeId,
        target: edge.target as CrewCanvasNodeId,
      };
    })
    .filter((edge): edge is CrewCanvasEdgeDraft => edge !== null);
  const nodePositions: Record<string, { x: number; y: number }> = {};
  const nodeSizes: Record<string, CrewCanvasNodeSize> = {};

  for (const node of nodes) {
    if (node.position) nodePositions[node.id] = node.position;
    if (node.type === 'crew') {
      const size = crewGraphNodeSize(node);
      if (size) nodeSizes[node.id] = size;
    }
  }

  return {
    selectedNodeId: null,
    nodes: draftNodes,
    edges: draftEdges,
    insertionOrder: draftNodes.map((node) => node.nodeId),
    nodePositions,
    nodeSizes,
  };
}

export function draftToCrewGraph(args: {
  draft: CrewCanvasDraft;
  crew?: { assetId: string; name: string; description: string; status?: string };
  availableAgents: CrewLibraryOption[];
  availableTasks: CrewLibraryOption[];
  availableTools: CrewToolOption[];
}): CrewGraph {
  const { draft, crew, availableAgents, availableTasks, availableTools } = args;

  const agentsById = new Map(availableAgents.map((agent) => [agent.assetId, agent]));
  const tasksById = new Map(availableTasks.map((task) => [task.assetId, task]));
  const toolsByKey = new Map(availableTools.map((tool) => [tool.key, tool]));

  const crewNodeId = crew ? toCrewNodeId(crew.assetId) : null;
  const crewNodeSize = crewNodeId ? resolveCrewContainerSize(draft, crewNodeId) : null;
  const childNodeProps = crewNodeId
    ? {
        parentId: crewNodeId,
        extent: 'parent' as const,
      }
    : {};

  const crewNode: CrewGraphNode | null = crew
    ? {
        id: crewNodeId as NonNullable<typeof crewNodeId>,
        type: 'crew',
        position: { x: 32, y: 32 },
        data: {
          kind: 'crew',
          assetId: crew.assetId,
          name: crew.name,
          subtitle: crew.description || crew.status || 'Crew container',
        },
        draggable: false,
        selectable: true,
        style: crewNodeSize ?? CREW_CONTAINER_DEFAULT_SIZE,
      }
    : null;

  const sortedDraftNodes = getSortedDraftNodes(draft);

  const nodeIndexForLane = createLaneIndexCounter();
  const childNodes = sortedDraftNodes.map((node): CrewGraphNode => {
    const index = nodeIndexForLane(node);
    if (node.kind === 'placeholder') {
      return {
        id: node.nodeId,
        type: 'placeholder',
        position: draft.nodePositions[node.nodeId] ?? getDefaultPlaceholderNodePosition(index),
        ...childNodeProps,
        data: {
          kind: 'placeholder',
          label: 'Assign Agent or Task',
          subtitle: 'Right-click to bind an existing asset.',
        },
        selectable: true,
      };
    }

    if (node.kind === 'agent') {
      const agent = agentsById.get(node.assetId);
      const toolNames = unique(agent?.toolKeys ?? []).map((toolKey) => toolsByKey.get(toolKey)?.name ?? toolKey);
      return {
        id: node.nodeId,
        type: 'agent',
        position: draft.nodePositions[node.nodeId] ?? getDefaultCrewNodePosition(index, 'agent'),
        ...childNodeProps,
        data: {
          kind: 'agent',
          assetId: node.assetId,
          versionId: node.versionId,
          name: agent?.name ?? 'Unknown agent',
          subtitle: agent?.subtitle ?? 'Agent asset unavailable',
          toolNames,
        },
        selectable: true,
      };
    }

    const task = tasksById.get(node.assetId);
    const toolNames = unique(task?.toolKeys ?? []).map((toolKey) => toolsByKey.get(toolKey)?.name ?? toolKey);
    return {
      id: node.nodeId,
      type: 'task',
      position: draft.nodePositions[node.nodeId] ?? getDefaultCrewNodePosition(index, 'task'),
      ...childNodeProps,
      data: {
        kind: 'task',
        assetId: node.assetId,
        versionId: node.versionId,
        name: task?.name ?? 'Unknown task',
        subtitle: task?.subtitle ?? 'Task asset unavailable',
        toolNames,
      },
      selectable: true,
    };
  });

  const visibleNodes = [crewNode, ...childNodes].filter((node): node is CrewGraphNode => node !== null);
  const visibleNodeIds = new Set<CrewGraphNodeId>(visibleNodes.map((node) => node.id));
  const editableEdges = draft.edges
    .filter((edge) => visibleNodeIds.has(edge.source as CrewGraphNodeId) && visibleNodeIds.has(edge.target as CrewGraphNodeId))
    .map((edge): CrewGraphEdge => toVisibleEditableEdge(edge));

  return {
    nodes: visibleNodes,
    edges: editableEdges,
  };
}

function createLaneIndexCounter() {
  const counts = {
    placeholder: 0,
    agent: 0,
    task: 0,
  };

  return (node: CrewCanvasNodeDraft) => {
    const index = counts[node.kind];
    counts[node.kind] += 1;
    return index;
  };
}

function validNodeSize(size: CrewCanvasNodeSize | undefined): CrewCanvasNodeSize | null {
  if (!size) return null;
  if (!Number.isFinite(size.width) || !Number.isFinite(size.height) || size.width <= 0 || size.height <= 0) return null;
  return size;
}

function resolveCrewContainerSize(draft: CrewCanvasDraft, crewNodeId: CrewGraphNodeId) {
  const savedSize = validNodeSize((draft.nodeSizes ?? {})[crewNodeId]);
  const autoSize = getAutoRequiredCrewContainerSize(draft);

  return {
    width: Math.max(CREW_CONTAINER_DEFAULT_SIZE.width, CREW_CONTAINER_MIN_SIZE.width, autoSize.width, savedSize?.width ?? 0),
    height: Math.max(CREW_CONTAINER_DEFAULT_SIZE.height, CREW_CONTAINER_MIN_SIZE.height, autoSize.height, savedSize?.height ?? 0),
  };
}

function getAutoRequiredCrewContainerSize(draft: CrewCanvasDraft) {
  const sortedDraftNodes = getSortedDraftNodes(draft);
  const nodeIndexForLane = createLaneIndexCounter();
  let maxRight = 0;
  let maxBottom = 0;

  for (const node of sortedDraftNodes) {
    const index = nodeIndexForLane(node);
    const position = draft.nodePositions[node.nodeId] ?? getDefaultNodePosition(node, index);
    const nodeSize = CREW_CANVAS_NODE_SIZE_BY_KIND[node.kind];
    maxRight = Math.max(maxRight, position.x + nodeSize.width);
    maxBottom = Math.max(maxBottom, position.y + nodeSize.height);
  }

  return {
    width: maxRight + CREW_CONTAINER_CHILD_PADDING.right,
    height: maxBottom + CREW_CONTAINER_CHILD_PADDING.bottom,
  };
}

function getDefaultNodePosition(node: CrewCanvasNodeDraft, index: number) {
  if (node.kind === 'placeholder') return getDefaultPlaceholderNodePosition(index);
  return getDefaultCrewNodePosition(index, node.kind);
}

function getSortedDraftNodes(draft: CrewCanvasDraft) {
  return draft.nodes.slice().sort((left, right) => {
    const leftIndex = draft.insertionOrder.indexOf(left.nodeId);
    const rightIndex = draft.insertionOrder.indexOf(right.nodeId);
    return (leftIndex === -1 ? left.insertedAt : leftIndex) - (rightIndex === -1 ? right.insertedAt : rightIndex);
  });
}

function toVisibleEditableEdge(edge: CrewCanvasEdgeDraft): CrewGraphEdge {
  const style = EDGE_STYLES[edge.kind];
  const handles = EDGE_HANDLES[edge.kind];
  return {
    id: edge.id,
    source: edge.source as CrewGraphNodeId,
    target: edge.target as CrewGraphNodeId,
    sourceHandle: handles.sourceHandle,
    targetHandle: handles.targetHandle,
    type: 'smoothstep',
    animated: edge.kind === 'task_sequence',
    markerEnd: { type: MarkerType.ArrowClosed, color: style.color },
    style: { stroke: style.color, strokeWidth: 2 },
    label: style.label,
    data: { kind: edge.kind },
  };
}

function isEditableEdgeKind(value: string): value is CrewCanvasEdgeKind {
  return value === 'agent_assignment' || value === 'task_context' || value === 'task_sequence';
}
