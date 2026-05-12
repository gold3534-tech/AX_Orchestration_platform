import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createKnowledge,
  deleteKnowledge,
  listKnowledge,
  replaceVersionKnowledge,
  uploadKnowledge,
  type KnowledgeCreatePayload,
} from '../../api/knowledge';
import { queryKeys } from '../../hooks/queryKeys';
import type { KnowledgeUploadInput } from './knowledgeTypes';

function unwrap<T>(result: { data?: T; error?: unknown }): T {
  if (result.error) throw result.error;
  return result.data as T;
}

export function useKnowledgeItems() {
  return useQuery({
    queryKey: queryKeys.knowledge.all(),
    queryFn: async () => unwrap(await listKnowledge()) ?? [],
  });
}

export function useCreateKnowledge() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: KnowledgeCreatePayload) => unwrap(await createKnowledge(payload)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.all() }),
  });
}

export function useUploadKnowledge() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: KnowledgeUploadInput) => unwrap(await uploadKnowledge(input)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.all() }),
  });
}

export function useDeleteKnowledge() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (knowledgeItemId: string) => unwrap(await deleteKnowledge(knowledgeItemId)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.all() }),
  });
}

export function useReplaceVersionKnowledge() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ versionId, knowledgeItemIds }: { versionId: string; knowledgeItemIds: string[] }) =>
      unwrap(await replaceVersionKnowledge(versionId, knowledgeItemIds)),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.all() });
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.version(variables.versionId) });
    },
  });
}
