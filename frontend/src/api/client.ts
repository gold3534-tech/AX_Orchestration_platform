import createClient from 'openapi-fetch';
import type { paths } from '../types/api.generated';
import { getStoredAccessToken } from '../hooks/useAuth';

export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? '';

export const client = createClient<paths>({
  baseUrl: apiBaseUrl,
});

client.use({
  onRequest({ request }: { request: Request }) {
    const accessToken = getStoredAccessToken();

    if (accessToken) {
      request.headers.set('Authorization', `Bearer ${accessToken}`);
    }

    return request;
  },
});
