import type { Edge, Node, XYPosition } from '@xyflow/react';

export type FlowNodeKind =
  | 'input'
  | 'start'
  | 'crew'
  | 'router'
  | 'hitl'
  | 'output'
  | 'tool'
  | 'execution_action';
export type FlowGraphNodeId = `${FlowNodeKind}:${string}`;
export type HitlOnNeedsRevision = 'retry_previous' | 'continue_with_feedback';
export type HitlFeedbackPropagation =
  | 'none'
  | 'needs_revision_only'
  | 'approved_and_needs_revision'
  | 'all_decisions';

export type FlowTransferInputType =
  | 'text'
  | 'structured'
  | 'raw'
  | 'image'
  | 'pdf'
  | 'text_file'
  | 'csv'
  | 'json_file'
  | 'docx'
  | 'audio'
  | 'video';

export type FlowTransferTransform =
  | 'identity_v1'
  | 'join_text_v1'
  | 'join_card_news_slides_v1'
  | 'json_stringify_v1';

export type FlowInputMappingDraft = {
  source: 'state' | 'node' | 'literal' | 'transform';
  path?: string;
  paths?: string[];
  nodeId?: FlowGraphNodeId;
  value?: unknown;
  inputType?: FlowTransferInputType;
  transform?: FlowTransferTransform;
  maxChars?: number;
  overflow?: 'fail' | 'truncate';
};

export type FlowBuilderNodeData = {
  kind: FlowNodeKind;
  label: string;
  fields?: Array<Record<string, unknown>>;
  triggerType?: 'manual';
  assetId?: string;
  versionId?: string;
  runtimeSnapshot?: Record<string, unknown>;
  inputMappings?: Record<string, FlowInputMappingDraft>;
  actionKey?: string;
  credentialProvider?: string;
  credentialId?: string;
  inputBindings?: Record<string, FlowInputMappingDraft>;
  configJson?: Record<string, unknown>;
  approvalMode?: 'never' | 'every_run';
  idempotencyKeyStrategy?: 'run_node_action_input_hash';
  outputMapping?: Record<string, unknown>;
  missingInputs?: string[];
  onOpenInputBinding?: (inputName: string) => void;
  conditions?: Array<Record<string, unknown>>;
  prompt?: string;
  allowedDecisions?: string[];
  onNeedsRevision?: HitlOnNeedsRevision;
  feedbackPropagation?: HitlFeedbackPropagation;
  maxAttempts?: number;
};

export type FlowBuilderNode = Node<FlowBuilderNodeData, FlowNodeKind> & { id: FlowGraphNodeId };
export type FlowBuilderEdge = Edge<{ route?: string }> & { source: FlowGraphNodeId; target: FlowGraphNodeId };

export function toFlowNodeId(kind: FlowNodeKind, id: string): FlowGraphNodeId {
  return `${kind}:${id}`;
}

export function isFlowGraphNodeId(value: string): value is FlowGraphNodeId {
  return /^(input|start|crew|router|hitl|output|tool|execution_action):/.test(value);
}

export function defaultFlowNodePosition(kind: FlowNodeKind): XYPosition {
  const positions: Record<FlowNodeKind, XYPosition> = {
    input: { x: 64, y: 180 },
    start: { x: 320, y: 180 },
    crew: { x: 520, y: 160 },
    router: { x: 860, y: 180 },
    hitl: { x: 860, y: 320 },
    output: { x: 1120, y: 180 },
    tool: { x: 600, y: 500 },
    execution_action: { x: 860, y: 500 },
  };
  return positions[kind];
}
