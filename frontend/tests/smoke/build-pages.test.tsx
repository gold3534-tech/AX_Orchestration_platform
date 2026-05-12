import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, RouterProvider, createMemoryRouter } from 'react-router-dom';
import { beforeEach, vi } from 'vitest';
import { appRoutes } from '../../src/app/routes';

function renderAtPath(pathname: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [pathname] });
  render(<RouterProvider router={router} />);
}

beforeEach(() => {
  window.localStorage.setItem('ai-oh.auth-token', 'smoke-token');
  vi.unstubAllGlobals();
});

test('renders the agents library shell with card/list toggle and create affordances', () => {
  renderAtPath('/build/agents');

  expect(screen.getByRole('heading', { name: /^agents$/i })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: /agent library/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /card/i })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('button', { name: /list/i })).toHaveAttribute('aria-pressed', 'false');
  expect(screen.getByRole('button', { name: /\+ new/i })).toBeEnabled();
});

test('renders the task form shell with the input preset mental model', () => {
  renderAtPath('/build/tasks');

  expect(screen.getByRole('heading', { name: /^tasks$/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /\+ new/i })).toBeInTheDocument();
  expect(screen.getByText(/Select a task card or list row to inspect details and manage it here/i)).toBeInTheDocument();
});

test('renders the tools library from the capability catalog only', async () => {
  const listCapabilities = vi.fn(async () => ({
    data: [
      {
        key: 'ax.nano_banana_image',
        type: 'agent_tool',
        label: 'Nano Banana 2 Image Generation',
        description: 'Generate image artifacts.',
        implementation_status: 'available',
        is_attachable: true,
        is_runtime_available: true,
        provider: 'google_gemini',
        auth_type: 'api_key',
        required_scopes: [],
        required_account_status: 'active',
        input_schema: {},
        config_schema: {},
        output_schema: {},
        supported_approval_modes: [],
        approval_policy: {},
        risk_level: 'write',
        artifact_input_requirements: {},
        implementation: 'ax_tool',
        policy_rationale: 'creative and research flexible tools stay agent_tool so agents can decide how to use them.',
      },
      {
        key: 'ax.google_drive_upload',
        type: 'Execution_Action',
        label: 'Google Drive Upload',
        description: 'Upload an AX artifact.',
        implementation_status: 'available',
        is_attachable: false,
        is_runtime_available: true,
        provider: 'google_workspace',
        auth_type: 'oauth2',
        required_scopes: [],
        required_account_status: 'active',
        input_schema: {},
        config_schema: {},
        output_schema: {},
        supported_approval_modes: ['never', 'every_run'],
        approval_policy: {},
        risk_level: 'upload',
        artifact_input_requirements: {},
        implementation: 'execution_action',
        policy_rationale: 'external storage actions are explicit execution actions.',
      },
    ],
  }));
  const getToolCatalog = vi.fn(async () => ({ data: [] }));
  vi.doMock('../../src/api/capabilities', () => ({ listCapabilities }));
  vi.doMock('../../src/api/tooling', () => ({ getToolCatalog }));
  vi.resetModules();
  const { ToolsLibraryPage } = await import('../../src/features/tools/ToolsLibraryPage');
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ToolsLibraryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(screen.getByRole('heading', { name: /^tools$/i })).toBeInTheDocument();
  expect(await screen.findByText(/Nano Banana 2 Image Generation/i)).toBeInTheDocument();
  expect(screen.getByText(/Google Drive Upload/i)).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: /Agent tools/i })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: /Execution actions/i })).toBeInTheDocument();
  expect(screen.queryByText(/Registered tools/i)).not.toBeInTheDocument();
  await waitFor(() => {
    expect(listCapabilities).toHaveBeenCalled();
  });
  expect(getToolCatalog).not.toHaveBeenCalled();
});
