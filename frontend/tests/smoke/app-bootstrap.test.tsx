import { useQueryClient } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach } from 'vitest';
import AppRoot from '../../src/app/AppRoot';

function QueryClientProbe() {
  useQueryClient();

  return <div data-testid="query-client-probe">ready</div>;
}

beforeEach(() => {
  window.localStorage.clear();
});

test('renders the login entry and the bootstrap provider tree when unauthenticated', () => {
  render(
    <AppRoot>
      <QueryClientProbe />
    </AppRoot>,
  );

  expect(screen.getByRole('heading', { name: /login/i })).toBeInTheDocument();
  expect(screen.getByTestId('query-client-probe')).toHaveTextContent('ready');
});
