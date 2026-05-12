import type { FormEvent } from 'react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiBaseUrl } from '../../api/client';
import { setStoredAccessToken } from '../../hooks/useAuth';

type PasswordLoginResponse = {
  access_token?: string;
};

function buildPasswordLoginUrl() {
  if (!apiBaseUrl) {
    return '/api/auth/password';
  }

  return new URL('/api/auth/password', apiBaseUrl).toString();
}

async function readErrorMessage(response: Response) {
  try {
    const data = await response.json();
    return typeof data.detail === 'string' && data.detail.trim() ? data.detail : null;
  } catch {
    return null;
  }
}

export function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setIsSubmitting(true);

    try {
      const response = await fetch(buildPasswordLoginUrl(), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });

      if (!response.ok) {
        setMessage((await readErrorMessage(response)) ?? 'Login failed. Please try again.');
        return;
      }

      const data = (await response.json()) as PasswordLoginResponse;
      if (!data.access_token) {
        setMessage('Login response was invalid. Please try again.');
        return;
      }

      setStoredAccessToken(data.access_token);
      navigate('/home', { replace: true });
    } catch {
      setMessage('Login failed. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen bg-[#F5E6D3] text-stone-950 lg:grid-cols-[minmax(0,1fr)_360px] xl:grid-cols-[minmax(0,1fr)_420px]">
      <section className="flex min-h-[48vh] items-center justify-center bg-[#F5E6D3] p-4 lg:min-h-screen lg:p-6">
        <video
          className="h-full max-h-[720px] w-full max-w-6xl rounded-md border border-stone-300 bg-stone-950 object-cover shadow-xl"
          src="/assets/auth/login-loop.mp4"
          autoPlay
          muted
          loop
          playsInline
          aria-label="AI workspace preview"
        />
      </section>

      <aside className="flex min-h-[52vh] items-center border-t border-stone-300 bg-white/90 px-6 py-10 shadow-sm lg:min-h-screen lg:border-l lg:border-t-0">
        <section className="w-full">
          <h1 className="text-2xl font-semibold text-stone-950">Login</h1>
          <p className="mt-2 text-sm text-stone-600">Use email/password or Google to enter the workspace.</p>

          <form className="mt-7 space-y-4" onSubmit={handleSubmit}>
            <label className="block text-sm font-medium text-stone-900">
              Email
              <input
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="mt-2 w-full rounded-md border border-stone-300 bg-white px-4 py-3 text-stone-950 outline-none transition focus:border-stone-700"
              />
            </label>

            <label className="block text-sm font-medium text-stone-900">
              Password
              <input
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="mt-2 w-full rounded-md border border-stone-300 bg-white px-4 py-3 text-stone-950 outline-none transition focus:border-stone-700"
              />
            </label>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full rounded-md bg-stone-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-stone-700 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {isSubmitting ? 'Signing in...' : 'Login'}
            </button>
          </form>

          {message ? <p className="mt-3 text-sm text-stone-700">{message}</p> : null}

          <div className="my-6 h-px bg-stone-200" />

          <a
            href="/api/auth/google"
            className="inline-flex w-full items-center justify-center rounded-md border border-stone-300 bg-white px-4 py-3 text-sm font-semibold text-stone-950 transition hover:border-stone-700"
          >
            Continue with Google
          </a>
        </section>
      </aside>
    </main>
  );
}
