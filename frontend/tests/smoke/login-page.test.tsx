import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appRoutes } from '../../src/app/routes';

describe('login route', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('redirects unauthenticated root traffic to /login', async () => {
    const router = createMemoryRouter(appRoutes, {
      initialEntries: ['/'],
    });

    render(<RouterProvider router={router} />);

    expect(await screen.findByRole('heading', { name: /login/i })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/login');
  });

  it('renders login actions on /login', async () => {
    const router = createMemoryRouter(appRoutes, {
      initialEntries: ['/login'],
    });

    render(<RouterProvider router={router} />);

    expect(await screen.findByRole('link', { name: /continue with google/i })).toHaveAttribute('href', '/api/auth/google');
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/ai workspace preview/i)).toHaveAttribute('src', '/assets/auth/login-loop.mp4');
  });

  it('stores the access token and navigates home after email login succeeds', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        access_token: 'email-access-token',
        refresh_token: 'email-refresh-token',
        expires_at: 1772848800,
        token_type: 'bearer',
      }),
    });
    vi.stubGlobal('fetch', fetchMock);
    const router = createMemoryRouter(appRoutes, {
      initialEntries: ['/login'],
    });

    render(<RouterProvider router={router} />);

    fireEvent.change(await screen.findByLabelText(/email/i), {
      target: { value: 'user@example.com' },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'correct-password' },
    });
    fireEvent.click(screen.getByRole('button', { name: /login/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/auth/password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: 'user@example.com', password: 'correct-password' }),
      });
    });
    await waitFor(() => {
      expect(window.localStorage.getItem('ai-oh.auth-token')).toBe('email-access-token');
      expect(router.state.location.pathname).toBe('/home');
    });
  });

  it('shows the backend error and stays on login when email login fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: vi.fn().mockResolvedValue({ detail: 'Email or password is incorrect.' }),
      }),
    );
    const router = createMemoryRouter(appRoutes, {
      initialEntries: ['/login'],
    });

    render(<RouterProvider router={router} />);

    fireEvent.change(await screen.findByLabelText(/email/i), {
      target: { value: 'user@example.com' },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'wrong-password' },
    });
    fireEvent.click(screen.getByRole('button', { name: /login/i }));

    expect(await screen.findByText('Email or password is incorrect.')).toBeInTheDocument();
    expect(window.localStorage.getItem('ai-oh.auth-token')).toBeNull();
    expect(router.state.location.pathname).toBe('/login');
  });

  it('starts authenticated root traffic on /login', async () => {
    window.localStorage.setItem('ai-oh.auth-token', 'smoke-token');

    const router = createMemoryRouter(appRoutes, {
      initialEntries: ['/'],
    });

    render(<RouterProvider router={router} />);

    expect(await screen.findByRole('heading', { name: /login/i })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/login');
  });

  it('keeps unauthenticated run traffic on the login surface', async () => {
    const router = createMemoryRouter(appRoutes, {
      initialEntries: ['/run'],
    });

    render(<RouterProvider router={router} />);

    expect(await screen.findByRole('heading', { name: /login/i })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/login');
  });

  it('redirects unauthenticated build traffic to /login', async () => {
    const router = createMemoryRouter(appRoutes, {
      initialEntries: ['/build/agents'],
    });

    render(<RouterProvider router={router} />);

    expect(await screen.findByRole('heading', { name: /login/i })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/login');
  });
});
