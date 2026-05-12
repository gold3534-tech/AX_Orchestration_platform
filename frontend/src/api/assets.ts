import type { components } from '../types/api.generated';
import type { paths } from '../types/api.generated';
import { client } from './client';

type AssetCreate = components['schemas']['AssetCreate'];
type AssetUpdate = components['schemas']['AssetUpdate'];
export type AssetUpdateRequest = AssetUpdate & {
  name?: string;
  description?: string | null;
};
type ListAssetsQuery = paths['/api/assets']['get']['parameters']['query'];
type AssetType = AssetCreate['type'];

function normalizeListAssetsQuery(query?: ListAssetsQuery | AssetType) {
  if (typeof query === 'string') {
    return { type: query } satisfies ListAssetsQuery;
  }

  return query;
}

export function listAssets(query?: ListAssetsQuery | AssetType) {
  return client.GET('/api/assets', {
    params: normalizeListAssetsQuery(query) === undefined ? undefined : { query: normalizeListAssetsQuery(query) },
  });
}

export function getAsset(assetId: string) {
  return client.GET('/api/assets/{asset_id}', {
    params: {
      path: {
        asset_id: assetId,
      },
    },
  });
}

export function createAsset(body: AssetCreate) {
  return client.POST('/api/assets', {
    body,
  });
}

export function updateAsset(assetId: string, body: AssetUpdateRequest) {
  return client.PATCH('/api/assets/{asset_id}', {
    params: {
      path: {
        asset_id: assetId,
      },
    },
    body,
  });
}

export function deleteAsset(assetId: string) {
  return client.DELETE('/api/assets/{asset_id}', {
    params: {
      path: {
        asset_id: assetId,
      },
    },
  });
}

export function listAssetVersions(assetId: string) {
  return client.GET('/api/assets/{asset_id}/versions', {
    params: {
      path: {
        asset_id: assetId,
      },
    },
  });
}

export function getAssetVersion(assetId: string, versionId: string) {
  return client.GET('/api/assets/{asset_id}/versions/{version_id}', {
    params: {
      path: {
        asset_id: assetId,
        version_id: versionId,
      },
    },
  });
}

export function restoreAssetVersion(assetId: string, versionId: string) {
  return client.POST('/api/assets/{asset_id}/versions/{version_id}/restore', {
    params: {
      path: {
        asset_id: assetId,
        version_id: versionId,
      },
    },
  });
}
