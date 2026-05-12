import type { components } from '../types/api.generated';
import { client } from './client';

type CredentialCreate = components['schemas']['CredentialCreate'];
type ExecutionBindingCreate = components['schemas']['ExecutionBindingCreate'];

export function listCredentials() {
  return client.GET('/api/credentials');
}

export function createCredential(body: CredentialCreate) {
  return client.POST('/api/credentials', { body });
}

export function createExecutionBinding(versionId: string, body: ExecutionBindingCreate) {
  return client.POST('/api/versions/{version_id}/bindings', {
    params: {
      path: {
        version_id: versionId,
      },
    },
    body,
  });
}

export function listVersionCapabilities(versionIds: string[]) {
  return client.GET('/api/version-capabilities', {
    params: {
      query: {
        version_ids: versionIds,
      },
    },
  });
}
