import type { Edge, Node, XYPosition } from '@xyflow/react';

export type CrewAgentNodeId = `agent:${string}`;
export type CrewTaskNodeId = `task:${string}`;
export type CrewContainerNodeId = `crew:${string}`;
export type CrewPlaceholderNodeId = `placeholder:${string}`;

export type CrewGraphNodeId =
  | CrewAgentNodeId
  | CrewTaskNodeId
  | CrewContainerNodeId
  | CrewPlaceholderNodeId;

export type CrewGraphNodeKind = 'crew' | 'placeholder' | 'agent' | 'task';
export type CrewGraphEdgeKind = 'agent_assignment' | 'task_context' | 'task_sequence';

export type CrewGraphAgentNodeData = {
  kind: 'agent';
  assetId: string;
  versionId: string;
  name: string;
  subtitle: string;
  toolNames: string[];
};

export type CrewGraphTaskNodeData = {
  kind: 'task';
  assetId: string;
  versionId: string;
  name: string;
  subtitle: string;
  toolNames: string[];
};

export type CrewGraphCrewNodeData = {
  kind: 'crew';
  assetId: string;
  name: string;
  subtitle: string;
};

export type CrewGraphPlaceholderNodeData = {
  kind: 'placeholder';
  label: string;
  subtitle: string;
};

export type CrewGraphNodeData =
  | CrewGraphCrewNodeData
  | CrewGraphPlaceholderNodeData
  | CrewGraphAgentNodeData
  | CrewGraphTaskNodeData;

export type CrewGraphEdgeData =
  | {
      kind: 'agent_assignment';
    }
  | {
      kind: 'task_context';
    }
  | {
      kind: 'task_sequence';
    };

export type CrewAgentNode = Node<CrewGraphAgentNodeData, 'agent'> & { id: CrewAgentNodeId };
export type CrewTaskNode = Node<CrewGraphTaskNodeData, 'task'> & { id: CrewTaskNodeId };
export type CrewContainerNode = Node<CrewGraphCrewNodeData, 'crew'> & { id: CrewContainerNodeId };
export type CrewPlaceholderNode = Node<CrewGraphPlaceholderNodeData, 'placeholder'> & { id: CrewPlaceholderNodeId };

export type CrewGraphNode = CrewContainerNode | CrewPlaceholderNode | CrewAgentNode | CrewTaskNode;
export type CrewGraphEdge = Edge<CrewGraphEdgeData> & { source: CrewGraphNodeId; target: CrewGraphNodeId };

export type CrewGraph = {
  nodes: CrewGraphNode[];
  edges: CrewGraphEdge[];
};

export function toAgentNodeId(assetId: string): CrewAgentNodeId {
  return `agent:${assetId}`;
}

export function toTaskNodeId(assetId: string): CrewTaskNodeId {
  return `task:${assetId}`;
}

export function toCrewNodeId(assetId: string): CrewContainerNodeId {
  return `crew:${assetId}`;
}

export function nodeKindFromId(id: string): CrewGraphNodeKind | null {
  if (id.startsWith('crew:')) return 'crew';
  if (id.startsWith('placeholder:')) return 'placeholder';
  if (id.startsWith('agent:')) return 'agent';
  if (id.startsWith('task:')) return 'task';
  return null;
}

export function isCrewGraphNodeId(value: string): value is CrewGraphNodeId {
  return nodeKindFromId(value) !== null;
}

export function getDefaultCrewNodePosition(index: number, lane: 'agent' | 'task'): XYPosition {
  const row = Math.floor(index / 3);
  const col = index % 3;

  const baseX = 96;
  const baseY = lane === 'task' ? 80 : 320;

  return {
    x: baseX + col * 280,
    y: baseY + row * 140,
  };
}

export function getDefaultPlaceholderNodePosition(index: number): XYPosition {
  const column = Math.floor(index / 2);
  const isTopRow = index % 2 === 0;

  return {
    x: 96 + column * 280,
    y: isTopRow ? 80 : 320,
  };
}
