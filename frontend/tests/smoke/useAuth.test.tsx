import { act } from '@testing-library/react';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, test, vi } from 'vitest';
import { useAuth } from '../../src/hooks/useAuth';

function AuthProbe() {
  const { accessToken } = useAuth();

  return <div data-testid="access-token">{accessToken ?? 'empty'}</div>;
}

describe('useAuth', () => {
  afterEach(() => {
    window.localStorage.clear();
    vi.unstubAllGlobals();
  });

  test('updates when another tab changes the stored auth token', async () => {
    render(<AuthProbe />);

    expect(screen.getByTestId('access-token')).toHaveTextContent('empty');

    act(() => {
      window.localStorage.setItem('ai-oh.auth-token', 'cross-tab-token');
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: 'ai-oh.auth-token',
          newValue: 'cross-tab-token',
          storageArea: window.localStorage,
          url: window.location.href,
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId('access-token')).toHaveTextContent('cross-tab-token');
    });
  });
});
