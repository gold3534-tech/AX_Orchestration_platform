import { render, screen, waitFor } from '@testing-library/react';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';
import { beforeEach } from 'vitest';
import App from '../../src/app/App';
import { appRoutes } from '../../src/app/routes';

function renderAtPath(pathname: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [pathname] });
  render(<RouterProvider router={router} />);
  return router;
}

beforeEach(() => {
  window.localStorage.setItem('ai-oh.auth-token', 'smoke-token');
});

test('keeps the build tab active on build tasks routes', () => {
  renderAtPath('/build/tasks');

  expect(screen.getByRole('tab', { name: /home/i })).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: /build/i })).toHaveAttribute('aria-current', 'page');
  expect(screen.getByRole('heading', { name: /^tasks$/i })).toBeInTheDocument();
});

test('keeps the home tab active on the home route', () => {
  renderAtPath('/home');

  expect(screen.getByRole('tab', { name: /home/i })).toHaveAttribute('aria-current', 'page');
  expect(screen.getByRole('heading', { name: /^home$/i })).toBeInTheDocument();
  expect(screen.queryByRole('navigation', { name: /build sections/i })).not.toBeInTheDocument();
});

test('keeps the run tab active on the run route', () => {
  renderAtPath('/run');

  expect(screen.getByRole('tab', { name: /run/i })).toHaveAttribute('aria-current', 'page');
  expect(screen.getByRole('heading', { name: /^run$/i })).toBeInTheDocument();
});

test('redirects unauthenticated run routes to login', async () => {
  window.localStorage.removeItem('ai-oh.auth-token');

  const router = createMemoryRouter(appRoutes, { initialEntries: ['/run'] });

  render(<RouterProvider router={router} />);

  expect(await screen.findByRole('heading', { name: /login/i })).toBeInTheDocument();
  expect(router.state.location.pathname).toBe('/login');
});

test('redirects the root route to login', async () => {
  const router = renderAtPath('/');

  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/login');
  });
  expect(screen.getByRole('heading', { name: /login/i })).toBeInTheDocument();
});

test('renders unknown routes as a public not-found page outside the app shell', () => {
  const router = renderAtPath('/does-not-exist');

  expect(router.state.location.pathname).toBe('/does-not-exist');
  expect(screen.getByRole('heading', { name: /page not found/i })).toBeInTheDocument();
  expect(screen.queryByRole('application', { name: /ai oh frontend/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('tab', { name: /build/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: /^agents$/i })).not.toBeInTheDocument();
});

test('renders the primary build and run navigation shell', () => {
  renderAtPath('/home');

  expect(screen.getByRole('tab', { name: /home/i })).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: /build/i })).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: /run/i })).toBeInTheDocument();

  expect(screen.getByRole('heading', { name: /^home$/i })).toBeInTheDocument();
  expect(screen.queryByRole('navigation', { name: /build sections/i })).not.toBeInTheDocument();
});
