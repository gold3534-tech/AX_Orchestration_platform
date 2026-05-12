import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AgentsPage } from '../../src/features/agents/AgentsPage';

const agentHookMocks = vi.hoisted(() => ({
  useAgentsLibrary: vi.fn(),
  useCreateAgent: vi.fn(),
  useUpdateAgent: vi.fn(),
  useDeleteAgent: vi.fn(),
}));

vi.mock('../../src/features/agents/hooks', () => agentHookMocks);

function renderPage() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AgentsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function mockAgentsLibraryState(overrides: Partial<ReturnType<typeof agentHookMocks.useAgentsLibrary>> = {}) {
  agentHookMocks.useAgentsLibrary.mockReturnValue({
    agents: [],
    tools: [],
    skills: [],
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  });
  agentHookMocks.useCreateAgent.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  agentHookMocks.useUpdateAgent.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  agentHookMocks.useDeleteAgent.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
}

test('renders a loading state when the agents library is loading', () => {
  mockAgentsLibraryState({ isLoading: true });

  renderPage();

  expect(screen.getByText(/loading/i)).toBeInTheDocument();
});

test('renders an empty state when the agents library has no agents', () => {
  mockAgentsLibraryState();

  renderPage();

  expect(screen.getByText(/no agents yet/i)).toBeInTheDocument();
});

test('renders an error state when the agents library fails to load', () => {
  mockAgentsLibraryState({
    isError: true,
    error: new Error('boom'),
  });

  renderPage();

  expect(screen.getByText(/unable to load agents/i)).toBeInTheDocument();
});
