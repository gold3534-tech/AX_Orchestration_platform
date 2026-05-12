import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  disconnectConnectedAccount,
  listConnectedAccountProviders,
  listConnectedAccounts,
  startConnectedAccountOAuth,
} from '../../api/connectedAccounts';
import { deleteProviderCredential, listCredentials, upsertProviderCredential } from '../../api/credentials';
import { queryKeys } from '../../hooks/queryKeys';
import type { components } from '../../types/api.generated';
import type { ConnectedAccountOAuthStartRequest } from './connectedAccountTypes';

type CredentialResponse = components['schemas']['CredentialResponse'];

type ApiResult<TData> = {
  data?: TData;
  error?: unknown;
};

function unwrapResult<TData>({ data, error }: ApiResult<TData>) {
  if (error) {
    throw error;
  }

  return data;
}

export function useCredentials() {
  const query = useQuery({
    queryKey: queryKeys.runtime.credentials(),
    queryFn: async () => unwrapResult(await listCredentials()) ?? [],
  });
  const credentials = query.data ?? [];

  return {
    credentials,
    credentialsByProvider: new Map(credentials.map((credential: CredentialResponse) => [credential.provider, credential])),
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
  };
}

export function useUpsertCredential() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ provider, apiKey, label }: { provider: string; apiKey: string; label: string }) =>
      unwrapResult(await upsertProviderCredential(provider, { api_key: apiKey, label })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.runtime.credentials() });
    },
  });
}

export function useDeleteCredential() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (provider: string) => {
      const result = await deleteProviderCredential(provider);
      if (result.error) {
        throw result.error;
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.runtime.credentials() });
    },
  });
}

export function useConnectedAccountProviders() {
  const query = useQuery({
    queryKey: queryKeys.connectedAccounts.providers(),
    queryFn: async () => unwrapResult(await listConnectedAccountProviders()) ?? [],
  });

  return {
    providers: query.data ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
  };
}

export function useConnectedAccounts() {
  const query = useQuery({
    queryKey: queryKeys.connectedAccounts.all(),
    queryFn: async () => unwrapResult(await listConnectedAccounts()) ?? [],
  });

  return {
    accounts: query.data ?? [],
    accountsByProvider: new Map((query.data ?? []).map((account) => [account.provider, account])),
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
  };
}

export function useStartConnectedAccountOAuth() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (body: ConnectedAccountOAuthStartRequest) =>
      unwrapResult(await startConnectedAccountOAuth(body)),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.connectedAccounts.all() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.connectedAccounts.providers() });
    },
  });
}

export function useDisconnectConnectedAccount() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (provider: string) => {
      const result = await disconnectConnectedAccount(provider);
      if (result.error) {
        throw result.error;
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.connectedAccounts.all() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.connectedAccounts.providers() });
    },
  });
}
