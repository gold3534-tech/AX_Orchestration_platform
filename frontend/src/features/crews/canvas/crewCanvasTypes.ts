import type { XYPosition } from '@xyflow/react';

export type CrewCanvasProcess = 'sequential' | 'hierarchical';
export type CrewCanvasAction = 'save' | 'validate' | 'publish';

export type CrewCanvasCrewNodeId = `crew:${string}`;
export type CrewCanvasPlaceholderNodeId = `placeholder:${string}`;
export type CrewCanvasAgentNodeId = `agent:${string}`;
export type CrewCanvasTaskNodeId = `task:${string}`;

export type CrewCanvasNodeId =
  | CrewCanvasCrewNodeId
  | CrewCanvasPlaceholderNodeId
  | CrewCanvasAgentNodeId
  | CrewCanvasTaskNodeId;

export type CrewCanvasPlaceholderNodeDraft = {
  nodeId: CrewCanvasPlaceholderNodeId;
  kind: 'placeholder';
  insertedAt: number;
};

export type CrewCanvasAgentNodeDraft = {
  nodeId: CrewCanvasAgentNodeId;
  kind: 'agent';
  assetId: string;
  versionId: string;
  insertedAt: number;
};

export type CrewCanvasTaskNodeDraft = {
  nodeId: CrewCanvasTaskNodeId;
  kind: 'task';
  assetId: string;
  versionId: string;
  insertedAt: number;
};

export type CrewCanvasNodeDraft = CrewCanvasPlaceholderNodeDraft | CrewCanvasAgentNodeDraft | CrewCanvasTaskNodeDraft;

export type CrewCanvasEdgeKind = 'agent_assignment' | 'task_context' | 'task_sequence';

export type CrewCanvasEdgeDraft = {
  id: string;
  kind: CrewCanvasEdgeKind;
  source: CrewCanvasNodeId;
  target: CrewCanvasNodeId;
};

export type CrewCanvasNodeSize = {
  width: number;
  height: number;
};

export type CrewCanvasDraft = {
  selectedNodeId: CrewCanvasNodeId | null;
  nodes: readonly CrewCanvasNodeDraft[];
  edges: readonly CrewCanvasEdgeDraft[];
  insertionOrder: readonly CrewCanvasNodeId[];
  nodePositions: Readonly<Record<string, XYPosition>>;
  nodeSizes?: Readonly<Record<string, CrewCanvasNodeSize>>;
};

export type CrewCanvasValidationError = {
  code:
    | 'missing_task'
    | 'placeholder_unbound'
    | 'agent_assignment_invalid_endpoint'
    | 'agent_assignment_missing'
    | 'agent_assignment_multiple'
    | 'task_context_invalid_endpoint'
    | 'task_context_self'
    | 'task_context_order'
    | 'task_sequence_invalid_endpoint'
    | 'task_sequence_self'
    | 'task_sequence_multiple_input'
    | 'task_sequence_multiple_output'
    | 'task_sequence_cycle';
  message: string;
  edgeId?: string;
  nodeId?: CrewCanvasNodeId;
};
