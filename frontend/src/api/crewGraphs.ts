import { apiBaseUrl } from './client';
import { getStoredAccessToken } from '../hooks/useAuth';

export type CrewGraphDocumentV1 = {
  schemaVersion: 1;
  layoutDirection?: string | null;
  viewport?: { x: number; y: number; zoom: number } | null;
  nodes: Array<{
    id: string;
    type: 'crew' | 'placeholder' | 'agent' | 'task';
    parentId?: string | null;
    extent?: string | null;
    position?: { x: number; y: number };
    style?: {
      width?: number;
      height?: number;
    } | null;
    data?: Record<string, unknown>;
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
    type: 'agent_assignment' | 'task_context' | 'task_sequence';
  }>;
  entities?: Record<string, unknown>;
};

export type CrewDraftEnvelope = {
  draft: {
    id: string;
    crew_asset_id: string;
    base_version_id: string | null;
    graph: Record<string, unknown>;
    validation: Record<string, unknown>;
    last_test_validation: Record<string, unknown>;
    created_at: string;
    updated_at: string;
  };
};

export type CrewPublishResponse = {
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

export type CrewDraftValidationResponse = Record<string, unknown>;

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

export async function getCrewGraphDraft(crewAssetId: string): Promise<CrewDraftEnvelope | null> {
  const response = await fetch(`${apiBaseUrl}/api/crew-graphs/${crewAssetId}/draft`, {
    method: 'GET',
    headers: buildHeaders(),
  });

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail ?? `Failed to load crew draft (${response.status})`);
  }

  return (await response.json()) as CrewDraftEnvelope;
}

export async function saveCrewGraphDraft(
  crewAssetId: string,
  graph: CrewGraphDocumentV1,
): Promise<CrewDraftEnvelope> {
  const response = await fetch(`${apiBaseUrl}/api/crew-graphs/${crewAssetId}/draft`, {
    method: 'PUT',
    headers: buildHeaders(),
    body: JSON.stringify({ graph }),
  });

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail ?? `Failed to save crew draft (${response.status})`);
  }

  return (await response.json()) as CrewDraftEnvelope;
}

export async function validateCrewGraphDraft(crewAssetId: string): Promise<CrewDraftValidationResponse> {
  const response = await fetch(`${apiBaseUrl}/api/crew-graphs/${crewAssetId}/validate`, {
    method: 'POST',
    headers: buildHeaders(),
  });

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail ?? `Failed to validate crew draft (${response.status})`);
  }

  return (await response.json()) as CrewDraftValidationResponse;
}

export async function publishCrewGraphDraft(crewAssetId: string): Promise<CrewPublishResponse> {
  const response = await fetch(`${apiBaseUrl}/api/crew-graphs/${crewAssetId}/publish`, {
    method: 'POST',
    headers: buildHeaders(),
  });

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail ?? `Failed to publish crew draft (${response.status})`);
  }

  return (await response.json()) as CrewPublishResponse;
}
