import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, test, vi } from 'vitest';

const {
  deleteCredentialSpy,
  disconnectConnectedAccountSpy,
  listConnectedAccountProvidersSpy,
  listConnectedAccountsSpy,
  listCredentialsSpy,
  redirectToOAuthAuthorizationSpy,
  startConnectedAccountOAuthSpy,
  upsertCredentialSpy,
} = vi.hoisted(() => ({
  deleteCredentialSpy: vi.fn(),
  disconnectConnectedAccountSpy: vi.fn(),
  listConnectedAccountProvidersSpy: vi.fn(),
  listConnectedAccountsSpy: vi.fn(),
  listCredentialsSpy: vi.fn(),
  redirectToOAuthAuthorizationSpy: vi.fn(),
  startConnectedAccountOAuthSpy: vi.fn(),
  upsertCredentialSpy: vi.fn(),
}));

vi.mock('../../src/api/credentials', () => ({
  deleteProviderCredential: deleteCredentialSpy,
  listCredentials: listCredentialsSpy,
  upsertProviderCredential: upsertCredentialSpy,
}));

vi.mock('../../src/api/connectedAccounts', () => ({
  disconnectConnectedAccount: disconnectConnectedAccountSpy,
  listConnectedAccountProviders: listConnectedAccountProvidersSpy,
  listConnectedAccounts: listConnectedAccountsSpy,
  startConnectedAccountOAuth: startConnectedAccountOAuthSpy,
}));

vi.mock('../../src/features/credentials/oauthRedirect', () => ({
  redirectToOAuthAuthorization: redirectToOAuthAuthorizationSpy,
}));

async function renderPage() {
  const { CredentialsPage } = await import('../../src/features/credentials/CredentialsPage');
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <CredentialsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  listCredentialsSpy.mockReset();
  listCredentialsSpy.mockResolvedValue({
    data: [
      {
        id: 'cred-openai',
        provider: 'openai',
        label: 'OpenAI API Key',
        enabled: true,
        created_at: '2026-04-28T00:00:00Z',
        updated_at: '2026-04-28T01:00:00Z',
      },
    ],
  });
  upsertCredentialSpy.mockReset();
  upsertCredentialSpy.mockResolvedValue({ data: {} });
  deleteCredentialSpy.mockReset();
  deleteCredentialSpy.mockResolvedValue({});
  listConnectedAccountProvidersSpy.mockReset();
  listConnectedAccountProvidersSpy.mockResolvedValue({
    data: [
      {
        provider: 'google_workspace',
        display_name: 'Google Workspace',
        label: 'Google Workspace',
        env_var: 'AX_GOOGLE_WORKSPACE_OAUTH',
        auth_type: 'oauth2',
        connect_label: 'Connect Google Workspace',
        reconnect_label: 'Reconnect Google Workspace',
        supports_disconnect: true,
        supports_test_connection: true,
        capabilities: ['sheets', 'drive', 'oauth2'],
        capability_keys: ['sheets', 'drive', 'oauth2'],
        default_scopes: ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive.file'],
      },
      {
        provider: 'meta_instagram',
        display_name: 'Instagram',
        label: 'Instagram',
        env_var: 'AX_META_INSTAGRAM_OAUTH',
        auth_type: 'oauth2',
        connect_label: 'Connect Instagram',
        reconnect_label: 'Reconnect Instagram',
        supports_disconnect: true,
        supports_test_connection: true,
        capabilities: ['instagram_publish', 'oauth2'],
        capability_keys: ['instagram_publish', 'oauth2'],
        default_scopes: ['instagram_basic', 'instagram_content_publish', 'pages_show_list'],
      },
    ],
  });
  listConnectedAccountsSpy.mockReset();
  listConnectedAccountsSpy.mockResolvedValue({ data: [] });
  startConnectedAccountOAuthSpy.mockReset();
  startConnectedAccountOAuthSpy.mockResolvedValue({
    data: {
      provider: 'meta_instagram',
      authorization_url: 'https://www.facebook.com/v24.0/dialog/oauth?state=state-1',
      state: 'state-1',
      expires_at: '2026-05-02T00:10:00Z',
    },
  });
  disconnectConnectedAccountSpy.mockReset();
  disconnectConnectedAccountSpy.mockResolvedValue({ data: { provider: 'meta_instagram', disconnected: true } });
  redirectToOAuthAuthorizationSpy.mockReset();
});

test('renders provider cards with connected state and disabled test buttons', async () => {
  await renderPage();

  expect(await screen.findByRole('heading', { name: /^credentials$/i })).toBeInTheDocument();
  expect(screen.getByText(/^OpenAI$/)).toBeInTheDocument();
  expect(screen.getByText(/^Anthropic$/)).toBeInTheDocument();
  expect(screen.getByText(/^Google Gemini$/)).toBeInTheDocument();
  expect(screen.getByText(/^Serper$/)).toBeInTheDocument();
  expect(screen.getByText(/^Firecrawl$/)).toBeInTheDocument();
  expect(await screen.findByText(/^Connected$/i)).toBeInTheDocument();
  expect(screen.getAllByRole('button', { name: /test connection/i })[0]).toBeDisabled();
});

test('connect modal submits a key and never redisplays it', async () => {
  await renderPage();

  fireEvent.click(await screen.findByRole('button', { name: /connect anthropic/i }));
  const input = screen.getByLabelText(/api key/i);
  fireEvent.change(input, { target: { value: 'anthropic-secret' } });
  fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

  await waitFor(() => {
    expect(upsertCredentialSpy).toHaveBeenCalledWith('anthropic', {
      api_key: 'anthropic-secret',
      label: 'Anthropic API Key',
    });
  });
  expect(screen.queryByDisplayValue('anthropic-secret')).not.toBeInTheDocument();
});

test('connect modal lets users reveal and hide the API key while typing', async () => {
  await renderPage();

  fireEvent.click(await screen.findByRole('button', { name: /connect anthropic/i }));
  const input = screen.getByLabelText(/api key/i);
  expect(input).toHaveAttribute('type', 'password');

  fireEvent.change(input, { target: { value: 'anthropic-secret' } });
  fireEvent.click(screen.getByRole('button', { name: /show key/i }));

  expect(screen.getByDisplayValue('anthropic-secret')).toHaveAttribute('type', 'text');

  fireEvent.click(screen.getByRole('button', { name: /hide key/i }));

  expect(screen.getByDisplayValue('anthropic-secret')).toHaveAttribute('type', 'password');
});

test('connect modal surfaces safe backend detail when saving fails', async () => {
  upsertCredentialSpy.mockResolvedValueOnce({
    error: { detail: 'Provider rejected this API key.' },
  });
  await renderPage();

  fireEvent.click(await screen.findByRole('button', { name: /connect anthropic/i }));
  fireEvent.change(screen.getByLabelText(/api key/i), { target: { value: 'anthropic-secret' } });
  fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

  expect(await screen.findByRole('dialog', { name: /credential action failed/i })).toBeInTheDocument();
  expect(screen.getByText('Provider rejected this API key.')).toBeInTheDocument();
  expect(screen.queryByDisplayValue('anthropic-secret')).not.toBeInTheDocument();
});

test('connect modal does not echo object validation payloads when saving fails', async () => {
  upsertCredentialSpy.mockResolvedValueOnce({
    error: { detail: { api_key: 'anthropic-secret' } },
  });
  await renderPage();

  fireEvent.click(await screen.findByRole('button', { name: /connect anthropic/i }));
  fireEvent.change(screen.getByLabelText(/api key/i), { target: { value: 'anthropic-secret' } });
  fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

  expect(await screen.findByRole('dialog', { name: /credential action failed/i })).toBeInTheDocument();
  expect(screen.getByText('Credential could not be saved.')).toBeInTheDocument();
  expect(screen.queryByText(/anthropic-secret/i)).not.toBeInTheDocument();
  expect(screen.queryByDisplayValue('anthropic-secret')).not.toBeInTheDocument();
});

test('delete confirmation calls provider delete API', async () => {
  await renderPage();

  fireEvent.click(await screen.findByRole('button', { name: /delete openai/i }));
  fireEvent.click(screen.getByRole('button', { name: /disconnect/i }));

  await waitFor(() => {
    expect(deleteCredentialSpy).toHaveBeenCalledWith('openai');
  });
});

test('connect instagram starts oauth and redirects to meta authorization url', async () => {
  await renderPage();

  fireEvent.click(await screen.findByRole('button', { name: /^connect instagram$/i }));

  await waitFor(() => {
    expect(startConnectedAccountOAuthSpy).toHaveBeenCalledWith({
      provider: 'meta_instagram',
      scopes: ['instagram_basic', 'instagram_content_publish', 'pages_show_list'],
      redirect_path: '/build/credentials',
    });
  });
  await waitFor(() => {
    expect(redirectToOAuthAuthorizationSpy).toHaveBeenCalledWith(
      'https://www.facebook.com/v24.0/dialog/oauth?state=state-1',
    );
  });
});

test('starting oauth disables other provider start buttons while pending', async () => {
  startConnectedAccountOAuthSpy.mockReturnValueOnce(new Promise(() => undefined));
  await renderPage();

  fireEvent.click(await screen.findByRole('button', { name: /^connect instagram$/i }));

  expect(await screen.findByRole('button', { name: /^starting\.\.\.$/i })).toBeDisabled();
  expect(screen.getByRole('button', { name: /^connect google workspace$/i })).toBeDisabled();

  fireEvent.click(screen.getByRole('button', { name: /^connect google workspace$/i }));
  expect(startConnectedAccountOAuthSpy).toHaveBeenCalledTimes(1);
});

test('connect instagram surfaces oauth start failures without redirecting', async () => {
  startConnectedAccountOAuthSpy.mockResolvedValueOnce({
    error: { detail: 'Meta Instagram OAuth is not configured.' },
  });
  await renderPage();

  fireEvent.click(await screen.findByRole('button', { name: /^connect instagram$/i }));

  expect(await screen.findByRole('dialog', { name: /credential action failed/i })).toBeInTheDocument();
  expect(screen.getByText('Meta Instagram OAuth is not configured.')).toBeInTheDocument();
  expect(redirectToOAuthAuthorizationSpy).not.toHaveBeenCalled();
});

test('connected instagram account shows account label and reconnect action', async () => {
  listConnectedAccountsSpy.mockResolvedValueOnce({
    data: [
      {
        id: 'connected-instagram',
        provider: 'meta_instagram',
        label: 'Instagram',
        auth_type: 'oauth2',
        provider_account_id: '17841405822304914',
        provider_account_label: 'Creator Page',
        status: 'active',
        scopes: ['instagram_basic', 'instagram_content_publish', 'pages_show_list'],
        missing_scopes: [],
        expires_at: '2026-05-02T01:00:00Z',
        last_checked_at: null,
        capability_keys: ['instagram_publish', 'oauth2'],
        created_at: '2026-05-02T00:00:00Z',
        updated_at: '2026-05-02T00:00:00Z',
      },
    ],
  });

  await renderPage();

  expect(await screen.findByText('Creator Page')).toBeInTheDocument();
  expect(screen.getByText('17841405822304914')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /^reconnect instagram$/i })).toBeInTheDocument();
});

test('connected account ui tolerates missing array fields from api payloads', async () => {
  listConnectedAccountProvidersSpy.mockResolvedValueOnce({
    data: [
      {
        provider: 'meta_instagram',
        display_name: 'Instagram',
        label: 'Instagram',
        env_var: 'AX_META_INSTAGRAM_OAUTH',
        auth_type: 'oauth2',
        connect_label: 'Connect Instagram',
        reconnect_label: 'Reconnect Instagram',
        supports_disconnect: true,
        supports_test_connection: true,
      },
    ],
  });
  listConnectedAccountsSpy.mockResolvedValueOnce({
    data: [
      {
        id: 'connected-instagram',
        provider: 'meta_instagram',
        label: 'Instagram',
        auth_type: 'oauth2',
        provider_account_id: '17841405822304914',
        provider_account_label: 'Creator Page',
        status: 'active',
        scopes: ['instagram_basic'],
        expires_at: null,
        last_checked_at: null,
        capability_keys: ['instagram_publish', 'oauth2'],
        created_at: '2026-05-02T00:00:00Z',
        updated_at: '2026-05-02T00:00:00Z',
      },
    ],
  });

  await renderPage();

  expect(await screen.findByText('Creator Page')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /^reconnect instagram$/i }));

  await waitFor(() => {
    expect(startConnectedAccountOAuthSpy).toHaveBeenCalledWith({
      provider: 'meta_instagram',
      scopes: [],
      redirect_path: '/build/credentials',
    });
  });
});
