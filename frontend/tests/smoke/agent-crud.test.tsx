import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AgentCard } from '../../src/features/agents/AgentCard';
import { AgentsPage } from '../../src/features/agents/AgentsPage';
import { AgentRow } from '../../src/features/agents/AgentRow';

const agentHookMocks = vi.hoisted(() => ({
  agentDisplayName: vi.fn((values: { role?: string }, fallback = 'Untitled Agent') => values.role?.trim() || fallback),
  useAgentsLibrary: vi.fn(),
  useCreateAgent: vi.fn(),
  useUpdateAgent: vi.fn(),
  useDeleteAgent: vi.fn(),
}));

vi.mock('../../src/features/agents/hooks', () => agentHookMocks);

function renderPage() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AgentsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function arrangeAgentsPage() {
  const createMutate = vi.fn(async () => undefined);
  const updateMutate = vi.fn(async () => undefined);
  const deleteMutate = vi.fn(async () => undefined);

  agentHookMocks.useAgentsLibrary.mockReturnValue({
    agents: [
      {
        assetId: 'agent-1',
        versionId: 'agent-v1',
        name: 'Research Lead',
        role: '조사',
        goal: '시장 신호를 수집합니다.',
        backstory: '탐색 중심 연구원',
        photoUrl: '',
        allowDelegation: false,
        llm: 'gpt-4o',
        function_calling_llm: 'gpt-4o-mini',
        max_iter: 12,
        max_rpm: 7,
        max_execution_time: 90,
        verbose: true,
        allow_delegation: true,
        reasoning: true,
        max_reasoning_attempts: 3,
        cache: true,
        respect_context_window: true,
        max_retry_limit: 4,
        multimodal: true,
        inject_date: true,
        date_format: '%d/%m/%Y',
        embedder: 'text-embedding-3-small',
        tools: ['Web Search'],
        toolConfigs: {},
        skills: ['Research'],
      },
    ],
    inputPresets: [
      { key: 'topic', label: 'Topic', inputType: 'string', description: 'Research topic.' },
    ],
    tools: ['Web Search', 'File Reader'],
    toolCatalog: [
      {
        id: 'web-search',
        tool_key: 'Web Search',
        name: 'Web Search',
        description: '',
        tool_type: 'python_class',
        module_path: '',
        class_name: '',
        default_config_json: {},
        config_schema_json: {},
        input_schema_json: {},
        ui_schema_json: {},
        required_env_vars: [],
        credential_requirements: [],
        enabled: true,
        created_at: '2026-05-01T00:00:00Z',
        updated_at: '2026-05-01T00:00:00Z',
      },
      {
        id: 'file-reader',
        tool_key: 'File Reader',
        name: 'File Reader',
        description: '',
        tool_type: 'python_class',
        module_path: '',
        class_name: '',
        default_config_json: {},
        config_schema_json: {},
        input_schema_json: {},
        ui_schema_json: {},
        required_env_vars: [],
        credential_requirements: [],
        enabled: true,
        created_at: '2026-05-01T00:00:00Z',
        updated_at: '2026-05-01T00:00:00Z',
      },
    ],
    skills: ['Research'],
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  });
  agentHookMocks.useCreateAgent.mockReturnValue({ mutateAsync: createMutate, isPending: false });
  agentHookMocks.useUpdateAgent.mockReturnValue({ mutateAsync: updateMutate, isPending: false });
  agentHookMocks.useDeleteAgent.mockReturnValue({ mutateAsync: deleteMutate, isPending: false });

  renderPage();

  return { createMutate, updateMutate, deleteMutate };
}

function getAgentItem(name: string) {
  const label = screen.getByText(name);
  const container = label.closest('button, tr');

  if (!(container instanceof HTMLElement)) {
    throw new Error(`Could not find an agent card or row for ${name}`);
  }

  return within(container);
}

function makeAgentListItem(overrides: Record<string, unknown> = {}) {
  return {
    assetId: 'agent-1',
    versionId: 'agent-v1',
    name: 'Creative Copywriter',
    role: 'Social Media Content Strategist',
    goal: '주제에 맞는 매력적이고 타깃 지향적인 문구를 설계합니다.',
    backstory: '캠페인 문구 설계 담당',
    photoUrl: '',
    allowDelegation: false,
    inputPresets: ['website_url'],
    tools: ['Web Search'],
    toolConfigs: {},
    knowledgeSources: [],
    skills: ['Research'],
    status: 'published',
    ...overrides,
  };
}


test('renders an agent card with an explicit photo slot and selection callback', () => {
  const agent = makeAgentListItem();
  const handleDetail = vi.fn();

  render(
    <AgentCard
      agent={agent}
      photoSlot={<img alt="Creative Copywriter portrait" src="https://example.com/agent.png" />}
      onDetail={handleDetail}
    />,
  );

  expect(screen.getByRole('heading', { name: 'Creative Copywriter' })).toBeInTheDocument();
  expect(screen.getByText('Social Media Content Strategist')).toBeInTheDocument();
  expect(screen.getByRole('img', { name: /creative copywriter portrait/i })).toBeInTheDocument();
  expect(screen.getByLabelText(/photo/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /creative copywriter/i }));

  expect(handleDetail).toHaveBeenCalledWith(expect.objectContaining({ assetId: 'agent-1' }));
});

test('renders an agent list row with photo and summary and supports selection', () => {
  const agent = makeAgentListItem({
    name: 'Research Analyst',
    role: 'Senior Technical Researcher',
    goal: '신뢰할 수 있는 최신 기술 트렌드를 분석합니다.',
    status: 'draft',
  });
  const handleDetail = vi.fn();

  render(
    <table>
      <tbody>
        <AgentRow agent={agent} onDetail={handleDetail} />
      </tbody>
    </table>,
  );

  const row = screen.getByText('Research Analyst').closest('tr');

  if (!(row instanceof HTMLTableRowElement)) {
    throw new Error('Expected AgentRow to render a table row');
  }

  const scopedRow = within(row);

  expect(scopedRow.getByLabelText(/photo/i)).toBeInTheDocument();
  expect(scopedRow.getByText('Senior Technical Researcher')).toBeInTheDocument();
  expect(scopedRow.getByText(/신뢰할 수 있는 최신 기술 트렌드를 분석합니다/i)).toBeInTheDocument();

  fireEvent.click(row);
  expect(handleDetail).toHaveBeenCalledWith(expect.objectContaining({ assetId: 'agent-1' }));
});

test('supports card/list toggle and create + inspector edit/delete flows', async () => {
  const { createMutate, updateMutate, deleteMutate } = arrangeAgentsPage();

  expect(screen.getByRole('button', { name: /card/i })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getAllByLabelText(/photo/i).length).toBeGreaterThan(0);

  fireEvent.click(screen.getByRole('button', { name: /list/i }));
  expect(screen.getByRole('button', { name: /list/i })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('columnheader', { name: /photo/i })).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /\+ new/i }));
  const createDialog = screen.getByRole('dialog', { name: /configure agent/i });
  const createModal = within(createDialog);

  expect(createModal.queryByLabelText(/agent name/i)).not.toBeInTheDocument();
  expect(createModal.getByLabelText(/role/i)).toBeInTheDocument();
  fireEvent.change(createModal.getByLabelText(/role/i), { target: { value: '전략' } });
  fireEvent.change(createModal.getByLabelText(/goal/i), { target: { value: '메시지 전략을 설계합니다.' } });
  fireEvent.change(createModal.getByLabelText(/backstory/i), { target: { value: '브랜드 리드' } });
  fireEvent.click(createModal.getByRole('button', { name: /save configuration/i }));

  await waitFor(() => {
    expect(createMutate).toHaveBeenCalledWith({
      values: expect.objectContaining({
        role: '전략',
        goal: '메시지 전략을 설계합니다.',
        backstory: '브랜드 리드',
      }),
      attachments: expect.objectContaining({
        tools: [],
        knowledgeSources: [],
      }),
    });
  });

  fireEvent.click(screen.getByText('Research Lead'));
  expect(screen.queryByLabelText(/^goal$/i)).not.toBeInTheDocument();
  expect(screen.getAllByText('시장 신호를 수집합니다.').length).toBeGreaterThan(0);

  fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
  const editDialog = screen.getByRole('dialog', { name: /configure agent/i });
  const editModal = within(editDialog);
  expect(editModal.getByLabelText(/backstory/i)).toHaveValue('탐색 중심 연구원');
  fireEvent.change(editModal.getByLabelText(/role/i), { target: { value: '수정된 역할' } });
  fireEvent.click(editModal.getByRole('button', { name: /save configuration/i }));

  await waitFor(() => {
    expect(updateMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        assetId: 'agent-1',
        baseVersionId: 'agent-v1',
        values: expect.objectContaining({
          role: '수정된 역할',
        }),
        attachments: expect.objectContaining({
          tools: ['Web Search'],
          knowledgeSources: [],
        }),
      }),
    );
  });

  fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
  fireEvent.click(screen.getByRole('button', { name: /confirm delete/i }));

  await waitFor(() => {
    expect(deleteMutate).toHaveBeenCalledWith('agent-1');
  });
});

test('defaults to card view and allows toggling to list view', () => {
  arrangeAgentsPage();

  expect(screen.getByRole('button', { name: /card/i })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getAllByLabelText(/photo/i).length).toBeGreaterThan(0);

  fireEvent.click(screen.getByRole('button', { name: /list/i }));
  expect(screen.getByRole('button', { name: /list/i })).toHaveAttribute('aria-pressed', 'true');
});

test('opens a create modal and submits the new agent values', async () => {
  const { createMutate } = arrangeAgentsPage();

  fireEvent.click(screen.getByRole('button', { name: /\+ new/i }));
  const dialog = screen.getByRole('dialog', { name: /configure agent/i });
  const modal = within(dialog);

  expect(modal.queryByLabelText(/agent name/i)).not.toBeInTheDocument();
  expect(modal.getByLabelText(/role/i)).toBeInTheDocument();
  fireEvent.change(modal.getByLabelText(/role/i), { target: { value: '전략' } });
  fireEvent.change(modal.getByLabelText(/goal/i), { target: { value: '메시지 전략을 설계합니다.' } });
  fireEvent.change(modal.getByLabelText(/backstory/i), { target: { value: '브랜드 리드' } });
  fireEvent.click(modal.getByRole('button', { name: /save configuration/i }));

  await waitFor(() => {
    expect(createMutate).toHaveBeenCalledWith({
      values: expect.objectContaining({
        role: '전략',
        goal: '메시지 전략을 설계합니다.',
        backstory: '브랜드 리드',
      }),
      attachments: expect.objectContaining({
        tools: [],
        knowledgeSources: [],
      }),
    });
  });
});

test('keeps in-progress agent modal edits across parent rerenders', () => {
  arrangeAgentsPage();
  const agentItem = getAgentItem('Research Lead');

  fireEvent.click(agentItem.getByText('Research Lead'));
  fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));

  const dialog = screen.getByRole('dialog', { name: /configure agent/i });
  const modal = within(dialog);
  fireEvent.change(modal.getByLabelText(/role/i), { target: { value: '입력 중인 역할' } });

  fireEvent.click(screen.getByRole('button', { name: /^list$/i }));

  expect(modal.getByLabelText(/role/i)).toHaveValue('입력 중인 역할');
});

test('focuses the agent dialog on open, closes on escape, and restores focus', async () => {
  arrangeAgentsPage();

  const newButton = screen.getByRole('button', { name: /\+ new/i });
  newButton.focus();
  fireEvent.click(newButton);

  const dialog = screen.getByRole('dialog', { name: /configure agent/i });

  await waitFor(() => {
    const activeElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    expect(dialog).toContainElement(activeElement);
  });

  fireEvent.keyDown(dialog, { key: 'Escape' });

  await waitFor(() => {
    expect(screen.queryByRole('dialog', { name: /configure agent/i })).not.toBeInTheDocument();
  });
  expect(newButton).toHaveFocus();
});

test('opens the agent modal for editing while keeping the inspector read-only', async () => {
  const { updateMutate } = arrangeAgentsPage();
  const agentItem = getAgentItem('Research Lead');

  fireEvent.click(agentItem.getByText('Research Lead'));
  expect(screen.queryByLabelText(/^goal$/i)).not.toBeInTheDocument();
  expect(screen.getAllByText('시장 신호를 수집합니다.').length).toBeGreaterThan(0);

  fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));

  const dialog = screen.getByRole('dialog', { name: /configure agent/i });
  const modal = within(dialog);

  expect(modal.getByLabelText(/backstory/i)).toHaveValue('탐색 중심 연구원');
  expect(modal.getByRole('switch', { name: /verbose logging/i })).toHaveAttribute('aria-checked', 'true');
  expect(modal.getByRole('switch', { name: /allow delegation/i })).toHaveAttribute('aria-checked', 'true');
  expect(modal.getByRole('switch', { name: /^reasoning$/i })).toHaveAttribute('aria-checked', 'true');
  expect(modal.getByLabelText(/max reasoning attempts/i)).toHaveValue(3);
  fireEvent.click(modal.getByRole('button', { name: /cost optimization/i }));
  expect(modal.getByLabelText(/max iter/i)).toHaveValue(12);
  fireEvent.click(modal.getByRole('button', { name: /model configuration/i }));
  expect(modal.getByLabelText(/^llm$/i)).toHaveValue('gpt-4o');
  expect(modal.getByLabelText(/function calling llm/i)).toHaveValue('gpt-4o-mini');
  fireEvent.click(modal.getByRole('button', { name: /date \/ time settings/i }));
  expect(modal.getByLabelText(/date format/i)).toHaveValue('%d/%m/%Y');
  fireEvent.change(modal.getByLabelText(/role/i), { target: { value: '수정된 역할' } });
  fireEvent.click(modal.getByRole('button', { name: /remove web search/i }));
  fireEvent.change(modal.getByLabelText(/tools/i), { target: { value: 'File Reader' } });
  fireEvent.click(modal.getAllByRole('button', { name: /add/i })[0]);
  fireEvent.click(modal.getByRole('button', { name: /save configuration/i }));

  await waitFor(() => {
    expect(updateMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        assetId: 'agent-1',
        baseVersionId: 'agent-v1',
        values: expect.objectContaining({
          role: '수정된 역할',
          llm: 'gpt-4o',
          function_calling_llm: 'gpt-4o-mini',
          max_iter: 12,
          max_rpm: 7,
          max_execution_time: 90,
          verbose: true,
          allow_delegation: true,
          reasoning: true,
          max_reasoning_attempts: 3,
          cache: true,
          respect_context_window: true,
          max_retry_limit: 4,
          multimodal: true,
          inject_date: true,
          date_format: '%d/%m/%Y',
          embedder: 'text-embedding-3-small',
        }),
        attachments: expect.objectContaining({
          tools: ['File Reader'],
          knowledgeSources: [],
        }),
      }),
    );
  });
});

test('opens edit modal for older agent fixtures without knowledge sources', () => {
  arrangeAgentsPage();
  const agentItem = getAgentItem('Research Lead');

  fireEvent.click(agentItem.getByText('Research Lead'));
  fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));

  expect(screen.getByRole('dialog', { name: /configure agent/i })).toBeInTheDocument();
  expect(screen.getByLabelText(/knowledge sources/i)).toBeInTheDocument();
});

test('deletes an agent via the inspector and confirms the delete action', async () => {
  const { deleteMutate } = arrangeAgentsPage();
  const agentItem = getAgentItem('Research Lead');

  fireEvent.click(agentItem.getByText('Research Lead'));
  fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
  fireEvent.click(screen.getByRole('button', { name: /confirm delete/i }));

  await waitFor(() => {
    expect(deleteMutate).toHaveBeenCalledWith('agent-1');
  });
});

test('agent modal submits Nano Banana tool config', async () => {
  const createMutate = vi.fn(async () => undefined);
  agentHookMocks.useAgentsLibrary.mockReturnValue({
    agents: [],
    agentPayloadsByAssetId: new Map(),
    inputPresets: [],
    tools: ['ax.nano_banana_image'],
    toolCatalog: [
      {
        id: 'ax.nano_banana_image',
        tool_key: 'ax.nano_banana_image',
        name: 'AX Nano Banana Image',
        description: 'Generate image artifacts.',
        tool_type: 'python_class',
        module_path: 'api.tools.nano_banana_image_tool',
        class_name: 'AXNanoBananaImageTool',
        default_config_json: { model: 'gemini-3.1-flash-image-preview', aspect_ratio: '1:1', image_size: '1K' },
        config_schema_json: {
          type: 'object',
          properties: {
            model: { type: 'string', enum: ['gemini-3.1-flash-image-preview', 'gemini-3-pro-image-preview'] },
            aspect_ratio: { type: 'string', enum: ['1:1', '9:16', '16:9'] },
            image_size: { type: 'string', enum: ['1K', '2K', '4K'] },
          },
          additionalProperties: false,
        },
        input_schema_json: {},
        ui_schema_json: {
          fields: {
            model: { label: 'Model', widget: 'select' },
            aspect_ratio: { label: 'Output ratio', widget: 'select' },
            image_size: { label: 'Image size', widget: 'select' },
          },
        },
        required_env_vars: [],
        credential_requirements: [],
        enabled: true,
        created_at: '2026-05-01T00:00:00Z',
        updated_at: '2026-05-01T00:00:00Z',
      },
    ],
    skills: [],
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  });
  agentHookMocks.useCreateAgent.mockReturnValue({ mutateAsync: createMutate, isPending: false });
  agentHookMocks.useUpdateAgent.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  agentHookMocks.useDeleteAgent.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  renderPage();

  fireEvent.click(screen.getByRole('button', { name: /\+ new/i }));
  const dialog = screen.getByRole('dialog', { name: /configure agent/i });
  const modal = within(dialog);
  fireEvent.change(modal.getByLabelText(/role/i), { target: { value: 'Image Director' } });
  fireEvent.change(modal.getByLabelText(/tools/i), { target: { value: 'ax.nano_banana_image' } });
  fireEvent.click(modal.getAllByRole('button', { name: /^add$/i })[0]);
  fireEvent.change(modal.getByLabelText(/output ratio/i), { target: { value: '16:9' } });
  fireEvent.change(modal.getByLabelText(/image size/i), { target: { value: '2K' } });
  fireEvent.click(modal.getByRole('button', { name: /save configuration/i }));

  await waitFor(() => {
    expect(createMutate).toHaveBeenCalledWith({
      values: expect.objectContaining({ role: 'Image Director' }),
      attachments: {
        tools: ['ax.nano_banana_image'],
        knowledgeSources: [],
        toolConfigs: {
          'ax.nano_banana_image': {
            model: 'gemini-3.1-flash-image-preview',
            aspect_ratio: '16:9',
            image_size: '2K',
          },
        },
      },
    });
  });
});
