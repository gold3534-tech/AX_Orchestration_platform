import { apiBaseUrl } from './client';
import { getStoredAccessToken } from '../hooks/useAuth';

export type TaskInputPresetCatalogItem = {
  id: string;
  key: string;
  label: string;
  input_type: string;
  description?: string | null;
  is_active: boolean;
  sort_order: number;
};

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

export async function listTaskInputPresets(includeInactive = false): Promise<TaskInputPresetCatalogItem[]> {
  const query = includeInactive ? '?include_inactive=true' : '';
  const response = await fetch(`${apiBaseUrl}/api/input-presets${query}`, {
    headers: buildHeaders(),
  });

  if (!response.ok) {
    throw new Error(`Failed to load task input presets (${response.status})`);
  }

  return (await response.json()) as TaskInputPresetCatalogItem[];
}
