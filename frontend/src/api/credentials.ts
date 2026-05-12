import type { components } from '../types/api.generated';
import { client } from './client';

export type CredentialProviderUpsert = components['schemas']['CredentialProviderUpsert'];

export function listCredentials() {
  return client.GET('/api/credentials');
}

export function upsertProviderCredential(provider: string, body: CredentialProviderUpsert) {
  return client.PUT('/api/credentials/{provider}', {
    params: { path: { provider } },
    body,
  });
}

export function deleteProviderCredential(provider: string) {
  return client.DELETE('/api/credentials/{provider}', {
    params: { path: { provider } },
  });
}
