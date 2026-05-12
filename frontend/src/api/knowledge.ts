import { apiBaseUrl, client } from './client';
import { getStoredAccessToken } from '../hooks/useAuth';
import type {
  KnowledgeCreatePayload,
  KnowledgeItem,
  KnowledgeUploadInput,
  VersionKnowledgeBinding,
} from '../features/knowledge/knowledgeTypes';

type ApiResult<TData> = {
  data?: TData;
  error?: unknown;
};

export type { KnowledgeCreatePayload };

export function listKnowledge() {
  return client.GET('/api/knowledge' as never) as Promise<ApiResult<KnowledgeItem[]>>;
}

export function createKnowledge(body: KnowledgeCreatePayload) {
  return client.POST('/api/knowledge' as never, { body } as never) as Promise<ApiResult<KnowledgeItem>>;
}

export async function uploadKnowledge(input: KnowledgeUploadInput): Promise<ApiResult<KnowledgeItem>> {
  const formData = new FormData();
  formData.append('file', input.file);
  if (input.name) formData.append('name', input.name);
  if (input.description) formData.append('description', input.description);

  const headers = new Headers();
  const accessToken = getStoredAccessToken();
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }

  const response = await fetch(`${apiBaseUrl}/api/knowledge/upload`, {
    method: 'POST',
    headers,
    body: formData,
  });

  if (!response.ok) {
    return {
      error: await response.json().catch(() => ({ detail: 'Knowledge upload failed.' })),
    };
  }

  return { data: (await response.json()) as KnowledgeItem };
}

export function deleteKnowledge(knowledgeItemId: string) {
  return client.DELETE('/api/knowledge/{knowledge_item_id}' as never, {
    params: { path: { knowledge_item_id: knowledgeItemId } },
  } as never) as Promise<ApiResult<void>>;
}

export function listVersionKnowledge(versionId: string) {
  return client.GET('/api/versions/{version_id}/knowledge' as never, {
    params: { path: { version_id: versionId } },
  } as never) as Promise<ApiResult<VersionKnowledgeBinding[]>>;
}

export function replaceVersionKnowledge(versionId: string, knowledgeItemIds: string[]) {
  return client.PUT('/api/versions/{version_id}/knowledge' as never, {
    params: { path: { version_id: versionId } },
    body: { knowledge_item_ids: knowledgeItemIds },
  } as never) as Promise<ApiResult<VersionKnowledgeBinding[]>>;
}
