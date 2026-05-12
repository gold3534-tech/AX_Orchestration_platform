import type { FlowGraphDocumentV1 } from '../../api/flowGraphs';
import type { FlowCanvasDraft, FlowCanvasEdgeDraft, FlowCanvasNodeDraft, PublishedCrewOption } from './hooks';
import { isFlowGraphNodeId } from './flowGraphTypes';
import type { FlowNodeKind } from './flowGraphTypes';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

const DEFAULT_EXECUTION_ACTION_IDEMPOTENCY_KEY_STRATEGY = 'run_node_action_input_hash';

function stringValue(...values: unknown[]) {
  return values.find((value): value is string => typeof value === 'string');
}

function recordValue(...values: unknown[]) {
  return values.find(isRecord) ?? {};
}

function executionActionApprovalMode(...values: unknown[]) {
  return values.includes('every_run') ? 'every_run' : 'never';
}

function executionActionDataToGraph(data: Record<string, unknown> | undefined) {
  return {
    action_key: stringValue(data?.actionKey, data?.action_key) ?? '',
    credential_provider: stringValue(data?.credentialProvider, data?.credential_provider) ?? null,
    credential_id: stringValue(data?.credentialId, data?.credential_id) ?? null,
    input_bindings: recordValue(data?.inputBindings, data?.input_bindings),
    config_json: recordValue(data?.configJson, data?.config_json),
    approval_mode: executionActionApprovalMode(data?.approvalMode, data?.approval_mode),
    idempotency_key_strategy:
      stringValue(data?.idempotencyKeyStrategy, data?.idempotency_key_strategy) ??
      DEFAULT_EXECUTION_ACTION_IDEMPOTENCY_KEY_STRATEGY,
    output_mapping: recordValue(data?.outputMapping, data?.output_mapping),
  };
}

function executionActionDataToDraft(data: Record<string, unknown> | undefined) {
  return {
    actionKey: stringValue(data?.action_key, data?.actionKey) ?? '',
    credentialProvider: stringValue(data?.credential_provider, data?.credentialProvider),
    credentialId: stringValue(data?.credential_id, data?.credentialId),
    inputBindings: recordValue(data?.input_bindings, data?.inputBindings),
    configJson: recordValue(data?.config_json, data?.configJson),
    approvalMode: executionActionApprovalMode(data?.approval_mode, data?.approvalMode),
    idempotencyKeyStrategy:
      stringValue(data?.idempotency_key_strategy, data?.idempotencyKeyStrategy) ??
      DEFAULT_EXECUTION_ACTION_IDEMPOTENCY_KEY_STRATEGY,
    outputMapping: recordValue(data?.output_mapping, data?.outputMapping),
  };
}

function isFlowNodeKind(value: string): value is FlowNodeKind {
  return (
    value === 'input' ||
    value === 'start' ||
    value === 'crew' ||
    value === 'router' ||
    value === 'hitl' ||
    value === 'output' ||
    value === 'tool' ||
    value === 'execution_action'
  );
}

function normalizeHitlData(data: Record<string, unknown> | undefined) {
  const value = data?.maxAttempts;

  return {
    maxAttempts: typeof value === 'number' && Number.isInteger(value) && value > 0 ? value : 3,
  };
}

function toDraftViewport(viewport: unknown): FlowCanvasDraft['viewport'] | undefined {
  if (viewport === null) {
    return null;
  }

  if (
    isRecord(viewport) &&
    typeof viewport.x === 'number' &&
    typeof viewport.y === 'number' &&
    typeof viewport.zoom === 'number'
  ) {
    return { x: viewport.x, y: viewport.y, zoom: viewport.zoom };
  }

  return undefined;
}

function toDraftEntities(entities: unknown): FlowCanvasDraft['entities'] | undefined {
  if (!isRecord(entities)) {
    return undefined;
  }

  const crews = isRecord(entities.crews)
    ? Object.fromEntries(
        Object.entries(entities.crews).filter((entry): entry is [string, Record<string, unknown>] =>
          isRecord(entry[1]),
        ),
      )
    : undefined;

  return {
    crews,
  };
}

function toDraftNode(node: FlowGraphDocumentV1['nodes'][number]): FlowCanvasNodeDraft | null {
  if (!isFlowGraphNodeId(node.id) || !isFlowNodeKind(node.type)) {
    return null;
  }

  return {
    id: node.id,
    type: node.type,
    position: node.position ?? { x: 0, y: 0 },
    data:
      node.type === 'hitl'
        ? normalizeHitlData(node.data)
        : node.type === 'execution_action'
          ? executionActionDataToDraft(node.data)
          : (node.data ?? {}),
  };
}

function toDraftEdge(edge: FlowGraphDocumentV1['edges'][number]): FlowCanvasEdgeDraft | null {
  if (!isFlowGraphNodeId(edge.source) || !isFlowGraphNodeId(edge.target)) {
    return null;
  }

  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    type: edge.type,
    data: edge.data ?? {},
  };
}

export function flowGraphDocumentToCanvasDraft(graph: FlowGraphDocumentV1 | Record<string, unknown>): FlowCanvasDraft {
  const document = graph as FlowGraphDocumentV1;
  const nodes = Array.isArray(document.nodes) ? document.nodes : [];
  const edges = Array.isArray(document.edges) ? document.edges : [];

  return {
    selectedNodeId: null,
    layoutDirection:
      typeof document.layoutDirection === 'string' || document.layoutDirection === null
        ? document.layoutDirection
        : undefined,
    viewport: toDraftViewport(document.viewport),
    entities: toDraftEntities(document.entities),
    nodes: nodes.map(toDraftNode).filter((node): node is FlowCanvasNodeDraft => node !== null),
    edges: edges.map(toDraftEdge).filter((edge): edge is FlowCanvasEdgeDraft => edge !== null),
  };
}

export function draftToFlowGraph({
  draft,
  publishedCrews,
}: {
  draft: FlowCanvasDraft;
  publishedCrews: PublishedCrewOption[];
}): FlowGraphDocumentV1 {
  const crewByVersionId = new Map(publishedCrews.map((crew) => [crew.versionId, crew]));
  const crewEntities: Record<string, Record<string, unknown>> = { ...(draft.entities?.crews ?? {}) };

  for (const node of draft.nodes) {
    if (node.type !== 'crew') {
      continue;
    }

    const versionId = typeof node.data.versionId === 'string' ? node.data.versionId : '';
    const crew = crewByVersionId.get(versionId);
    if (!crew) {
      continue;
    }

    crewEntities[crew.versionId] = {
      asset_id: crew.assetId,
      version_id: crew.versionId,
      version_no: crew.versionNo,
      name: crew.name,
      status: crew.status,
      runtime_snapshot_json: crew.runtimeSnapshot,
    };
  }

  return {
    schemaVersion: 1,
    layoutDirection: draft.layoutDirection ?? 'LR',
    viewport: draft.viewport,
    nodes: draft.nodes.map((node) => ({
      id: node.id,
      type: node.type,
      position: node.position,
      data:
        node.type === 'hitl'
          ? normalizeHitlData(node.data)
          : node.type === 'execution_action'
            ? executionActionDataToGraph(node.data)
            : node.data,
    })),
    edges: draft.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: edge.type,
      data: edge.data,
    })),
    entities: { crews: crewEntities },
  };
}
