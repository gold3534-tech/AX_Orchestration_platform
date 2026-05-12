import type {
  ConnectedAccountOAuthStartRequest,
  ConnectedAccountOAuthStartResponse,
  ConnectedAccountProvider,
  ConnectedAccountSummary,
} from '../features/credentials/connectedAccountTypes';
import { client } from './client';

type ApiResult<TData> = {
  data?: TData;
  error?: unknown;
  response: Response;
};

export function listConnectedAccountProviders() {
  return client.GET('/api/connected-accounts/providers' as never) as Promise<ApiResult<ConnectedAccountProvider[]>>;
}

export function listConnectedAccounts() {
  return client.GET('/api/connected-accounts' as never) as Promise<ApiResult<ConnectedAccountSummary[]>>;
}

export function startConnectedAccountOAuth(body: ConnectedAccountOAuthStartRequest) {
  return client.POST('/api/connected-accounts/oauth/start' as never, { body } as never) as Promise<
    ApiResult<ConnectedAccountOAuthStartResponse>
  >;
}

export function disconnectConnectedAccount(provider: string) {
  return client.DELETE('/api/connected-accounts/{provider}' as never, {
    params: { path: { provider } },
  } as never) as Promise<ApiResult<{ provider: string; disconnected: boolean }>>;
}
