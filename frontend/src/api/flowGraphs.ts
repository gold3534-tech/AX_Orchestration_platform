import { apiBaseUrl } from './client';
import { getStoredAccessToken } from '../hooks/useAuth';

export type FlowGraphNodeKind =
  | 'input'
  | 'start'
  | 'crew'
  | 'router'
  | 'hitl'
  | 'output'
  | 'tool'
  | 'execution_action';
export type FlowGraphEdgeKind = 'flow' | 'route' | 'tool_reference';

export type FlowGraphDocumentV1 = {
  schemaVersion: 1;
  layoutDirection?: string | null;
  viewport?: { x: number; y: number; zoom: number } | null;
  nodes: Array<{
    id: string;
    type: FlowGraphNodeKind;
    position?: { x: number; y: number };
    data?: Record<string, unknown>;
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
    type: FlowGraphEdgeKind;
    data?: Record<string, unknown>;
  }>;
  entities?: {
    crews?: Record<string, Record<string, unknown>>;
  };
};

export type PublishedCrewForFlow = {
  asset_id: string;
  version_id: string;
  version_no: number;
  name: string;
  description?: string | null;
  status: string;
  runtime_snapshot_json: Record<string, unknown>;
};

export type PublishedFlowForRun = {
  asset_id: string;
  version_id: string;
  version_no: number;
  name: string;
  description?: string | null;
  status: string;
  has_input_node: boolean;
};

export type FlowDraftEnvelope = {
  draft: {
    id: string;
    flow_asset_id: string;
    base_version_id: string | null;
    graph: FlowGraphDocumentV1 | Record<string, unknown>;
    validation: Record<string, unknown>;
    last_test_validation: Record<string, unknown>;
    created_at: string;
    updated_at: string;
  };
};

export type FlowPublishResponse = {
  already_published?: boolean;
  version: {
    id: string;
    asset_id: string;
    version_no: number;
    status: string;
    payload: Record<string, unknown>;
    runtime_snapshot_json: Record<string, unknown>;
    created_at: string;
  };
};

export type FlowDiagnosticResult = Record<string, unknown>;

function buildHeaders() {
  const accessToken = getStoredAccessToken();
  return {
    'Content-Type': 'application/json',
    ...(accessToken
      ? {
          Authorization: `Bearer ${accessToken}`,
        }
      : {}),
  };
}

async function readErrorDetail(response: Response) {
  try {
    const data = (await response.json()) as { detail?: unknown };
    if (typeof data?.detail === 'string') {
      return data.detail;
    }
  } catch {
    // ignore
  }

  return null;
}

export async function getFlowGraphDraft(flowAssetId: string): Promise<FlowDraftEnvelope | null> {
  const response = await fetch(`${apiBaseUrl}/api/flow-graphs/${flowAssetId}/draft`, {
    method: 'GET',
    headers: buildHeaders(),
  });

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail ?? `Failed to load flow draft (${response.status})`);
  }

  return (await response.json()) as FlowDraftEnvelope;
}

export async function saveFlowGraphDraft(
  flowAssetId: string,
  graph: FlowGraphDocumentV1,
): Promise<FlowDraftEnvelope> {
  const response = await fetch(`${apiBaseUrl}/api/flow-graphs/${flowAssetId}/draft`, {
    method: 'PUT',
    headers: buildHeaders(),
    body: JSON.stringify({ graph }),
  });

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail ?? `Failed to save flow draft (${response.status})`);
  }

  return (await response.json()) as FlowDraftEnvelope;
}

export async function validateFlowGraphDraft(flowAssetId: string): Promise<Record<string, unknown>> {
  const response = await fetch(`${apiBaseUrl}/api/flow-graphs/${flowAssetId}/validate`, {
    method: 'POST',
    headers: buildHeaders(),
  });

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail ?? `Failed to validate flow draft (${response.status})`);
  }

  return (await response.json()) as Record<string, unknown>;
}

export async function runFlowCompatibilityDiagnostics(
  flowAssetId: string,
  inputs: Record<string, unknown> = {},
): Promise<FlowDiagnosticResult> {
  const response = await fetch(`${apiBaseUrl}/api/flow-graphs/${flowAssetId}/diagnostics/compatibility`, {
    method: 'POST',
    headers: buildHeaders(),
    body: JSON.stringify({ inputs }),
  });

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail ?? `Failed to run compatibility diagnostics (${response.status})`);
  }

  return (await response.json()) as FlowDiagnosticResult;
}

export async function runFlowToolMockCallDiagnostics(flowAssetId: string): Promise<FlowDiagnosticResult> {
  const response = await fetch(`${apiBaseUrl}/api/flow-graphs/${flowAssetId}/diagnostics/tool-mock-call`, {
    method: 'POST',
    headers: buildHeaders(),
  });

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail ?? `Failed to run tool mock-call diagnostics (${response.status})`);
  }

  return (await response.json()) as FlowDiagnosticResult;
}

export async function publishFlowGraphDraft(flowAssetId: string): Promise<FlowPublishResponse> {
  const response = await fetch(`${apiBaseUrl}/api/flow-graphs/${flowAssetId}/publish`, {
    method: 'POST',
    headers: buildHeaders(),
  });

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail ?? `Failed to publish flow draft (${response.status})`);
  }

  return (await response.json()) as FlowPublishResponse;
}

export async function listPublishedCrewsForFlow(): Promise<PublishedCrewForFlow[]> {
  const response = await fetch(`${apiBaseUrl}/api/flow-graphs/published-crews`, {
    method: 'GET',
    headers: buildHeaders(),
  });

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail ?? `Failed to load published crews (${response.status})`);
  }

  const body = (await response.json()) as { crews?: PublishedCrewForFlow[] };
  return body.crews ?? [];
}

export async function listPublishedFlowsForRun(): Promise<PublishedFlowForRun[]> {
  const response = await fetch(`${apiBaseUrl}/api/flow-graphs/published-flows`, {
    method: 'GET',
    headers: buildHeaders(),
  });

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail ?? `Failed to load published flows (${response.status})`);
  }

  const body = (await response.json()) as { flows?: PublishedFlowForRun[] };
  return body.flows ?? [];
}
