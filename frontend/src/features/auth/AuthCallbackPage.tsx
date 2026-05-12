import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { apiBaseUrl } from '../../api/client';
import { setStoredAccessToken } from '../../hooks/useAuth';

type OAuthCallbackResponse = {
  access_token?: string;
};

const oauthCodeExchangePromises = new Map<string, Promise<string>>();

function buildOAuthCallbackUrl(search: string) {
  if (!apiBaseUrl) {
    return `/api/auth/callback${search}`;
  }

  const url = new URL('/api/auth/callback', apiBaseUrl);
  url.search = search;
  return url.toString();
}

function exchangeOAuthCode(code: string, search: string) {
  const existingPromise = oauthCodeExchangePromises.get(code);
  if (existingPromise) {
    return existingPromise;
  }

  const exchangePromise = fetch(buildOAuthCallbackUrl(search), {
    credentials: 'include',
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error('OAuth code exchange failed.');
      }

      const data = (await response.json()) as OAuthCallbackResponse;
      if (!data.access_token) {
        throw new Error('OAuth callback did not return an access token.');
      }

      return data.access_token;
    })
    .catch((error) => {
      oauthCodeExchangePromises.delete(code);
      throw error;
    });

  oauthCodeExchangePromises.set(code, exchangePromise);
  return exchangePromise;
}

export function AuthCallbackPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    let cancelled = false;

    async function completeLogin() {
      // Debug: log the full location so we can see whether Supabase returned a fragment
      if (typeof window !== 'undefined') {
        // eslint-disable-next-line no-console
        console.log('AuthCallbackPage loaded:', {
          href: window.location.href,
          pathname: window.location.pathname,
          search: window.location.search,
          hash: window.location.hash,
        });
      }

      // Supabase may return the session in the URL fragment (hash) after redirect.
      // Example: #access_token=...&refresh_token=...
      const hash = typeof window !== 'undefined' ? window.location.hash : '';
      if (hash && hash.includes('access_token=')) {
        const params = new URLSearchParams(hash.replace('#', '?'));
        const accessToken = params.get('access_token');
        if (accessToken) {
          setStoredAccessToken(accessToken);
          // Clear the hash and navigate to the app
          window.history.replaceState(window.history.state, '', window.location.pathname + window.location.search);
          navigate('/home', { replace: true });
          return;
        }
      }

      // Supabase PKCE flow returns an authorization code in the query string.
      // Exchange it through the backend so the app can store the resulting token.
      const code = searchParams.get('code');
      if (code) {
        try {
          const accessToken = await exchangeOAuthCode(code, window.location.search);
          setStoredAccessToken(accessToken);
          if (!cancelled) {
            navigate('/home', { replace: true });
          }
          return;
        } catch (error) {
          // eslint-disable-next-line no-console
          console.error(error);
        }

        if (cancelled) {
          return;
        }
        navigate('/login');
      }
    }

    completeLogin();

    return () => {
      cancelled = true;
    };
  }, [searchParams, navigate]);

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
      <p>로그인 처리 중...</p>
    </div>
  );
}
