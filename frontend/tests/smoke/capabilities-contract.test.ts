import { describe, expect, it, vi } from 'vitest';
import {
  CAPABILITY_TYPES,
  listCapabilities,
  listExecutionActions,
  type CapabilityCatalogItem,
} from '../../src/api/capabilities';
import {
  listConnectedAccountProviders,
  listConnectedAccounts,
  startConnectedAccountOAuth,
} from '../../src/api/connectedAccounts';
import { client } from '../../src/api/client';
import type { ConnectedAccountSummary } from '../../src/features/credentials/connectedAccountTypes';

describe('capability frontend contracts', () => {
  it('loads capability catalog through the API wrapper', async () => {
    const spy = vi.spyOn(client, 'GET').mockResolvedValueOnce({
      data: [{ key: 'ax.google_sheets', type: 'agent_tool', label: 'AX Google Sheets' }],
      error: undefined,
      response: new Response(),
    } as never);

    const result = await listCapabilities();

    expect(spy).toHaveBeenCalledWith('/api/capabilities');
    expect(result.data?.[0].key).toBe('ax.google_sheets');
  });

  it('loads execution actions through the API wrapper without reclassifying tools', async () => {
    const spy = vi.spyOn(client, 'GET').mockResolvedValueOnce({
      data: [{ key: 'ax.google_drive_upload', type: 'Execution_Action', label: 'Google Drive Upload' }],
      error: undefined,
      response: new Response(),
    } as never);

    const result = await listExecutionActions();

    expect(spy).toHaveBeenCalledWith('/api/execution-actions');
    expect(result.data?.[0].type).toBe('Execution_Action');
  });

  it('understands only the backend capability type literals', () => {
    const sheetsCapability: CapabilityCatalogItem = {
      key: 'ax.google_sheets',
      type: 'agent_tool',
      label: 'AX Google Sheets',
      description: 'Read and update Google Sheets.',
      implementation_status: 'planned',
      is_attachable: false,
      is_runtime_available: false,
      provider: 'google_workspace',
      auth_type: 'oauth2',
      required_scopes: ['https://www.googleapis.com/auth/spreadsheets'],
      required_account_status: 'active',
      input_schema: {
        type: 'object',
        properties: {
          operation: { type: 'string', enum: ['read_range', 'append_rows', 'update_values'] },
        },
      },
      config_schema: {
        type: 'object',
        properties: {
          append_rows_enabled: { type: 'boolean', default: true },
          update_values_enabled: { type: 'boolean', default: true },
        },
      },
      output_schema: { type: 'object' },
      supported_approval_modes: [],
      approval_policy: {},
      risk_level: 'write',
      artifact_input_requirements: {},
      implementation: 'ax_tool',
      policy_rationale: 'agent tool policy',
    };

    expect(CAPABILITY_TYPES).toEqual(['agent_tool', 'Execution_Action']);
    expect(sheetsCapability.type).toBe('agent_tool');
    expect(sheetsCapability.type).not.toBe('Execution_Action');
    expect(sheetsCapability.config_schema.properties).toMatchObject({
      append_rows_enabled: { type: 'boolean' },
      update_values_enabled: { type: 'boolean' },
    });
  });

  it('loads connected account summaries without secrets', async () => {
    const spy = vi.spyOn(client, 'GET').mockResolvedValueOnce({
      data: [{ provider: 'google_workspace', auth_type: 'oauth2', status: 'active' }],
      error: undefined,
      response: new Response(),
    } as never);

    const result = await listConnectedAccounts();

    expect(spy).toHaveBeenCalledWith('/api/connected-accounts');
    expect(JSON.stringify(result.data)).not.toContain('access_token');
    expect(JSON.stringify(result.data)).not.toContain('refresh_token');
    expect(JSON.stringify(result.data)).not.toContain('client_secret');
  });

  it('loads provider metadata and starts OAuth through connected account wrappers', async () => {
    const getSpy = vi.spyOn(client, 'GET').mockResolvedValueOnce({
      data: [{ provider: 'google_workspace', auth_type: 'oauth2', default_scopes: ['scope'] }],
      error: undefined,
      response: new Response(),
    } as never);
    const postSpy = vi.spyOn(client, 'POST').mockResolvedValueOnce({
      data: { provider: 'google_workspace', authorization_url: 'https://accounts.google.com', state: 'state' },
      error: undefined,
      response: new Response(),
    } as never);

    await listConnectedAccountProviders();
    await startConnectedAccountOAuth({
      provider: 'google_workspace',
      scopes: ['https://www.googleapis.com/auth/spreadsheets'],
      redirect_path: '/credentials',
    });

    expect(getSpy).toHaveBeenCalledWith('/api/connected-accounts/providers');
    expect(postSpy).toHaveBeenCalledWith('/api/connected-accounts/oauth/start', {
      body: {
        provider: 'google_workspace',
        scopes: ['https://www.googleapis.com/auth/spreadsheets'],
        redirect_path: '/credentials',
      },
    });
  });

  it('keeps connected account summaries token-free at the UI type boundary', () => {
    const account: ConnectedAccountSummary = {
      id: 'account-1',
      provider: 'google_workspace',
      label: 'Google Workspace',
      auth_type: 'oauth2',
      provider_account_id: 'workspace@example.com',
      provider_account_label: 'workspace@example.com',
      status: 'active',
      scopes: ['https://www.googleapis.com/auth/spreadsheets'],
      missing_scopes: [],
      expires_at: null,
      last_checked_at: null,
      capability_keys: ['sheets', 'drive', 'oauth2'],
      created_at: '2026-05-01T00:00:00Z',
      updated_at: '2026-05-01T00:00:00Z',
    };

    expect(Object.keys(account)).not.toEqual(expect.arrayContaining(['access_token', 'refresh_token', 'client_secret']));
  });
});
