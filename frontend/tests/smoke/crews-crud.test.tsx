import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, test, vi } from 'vitest';
import { CrewsPage } from '../../src/features/crews/CrewsPage';
import { buildCrewGraphDocument, toCrewAssetPayload, type CrewFormValues } from '../../src/features/crews/hooks';

const {
  updateAssetSpy,
  saveCrewDraftSpy,
  publishCrewDraftSpy,
  loadCrewDraftSpy,
  validateCrewDraftSpy,
  state,
} = vi.hoisted(() => ({
  updateAssetSpy: vi.fn().mockResolvedValue({ data: { id: 'crew-1' } }),
  saveCrewDraftSpy: vi.fn().mockResolvedValue({ draft: { id: 'draft-1' } }),
  loadCrewDraftSpy: vi.fn().mockResolvedValue(null),
  validateCrewDraftSpy: vi.fn().mockResolvedValue({ schemaVersion: 1 }),
  publishCrewDraftSpy: vi.fn().mockResolvedValue({ version: { version_no: 2 }, already_published: false }),
  state: {
    crewVersionId: 'crew-v1',
    processType: 'sequential',
    draftVariant: 'complete' as 'complete' | 'missing-agent' | 'multi-row' | 'stale-agent' | 'empty' | 'placeholder-only' | 'placeholder-with-task',
  },
}));

vi.mock('../../src/api/assets', async (importOriginal) => {
  const actual = (await importOriginal()) as typeof import('../../src/api/assets');

  return {
    ...actual,
    updateAsset: updateAssetSpy,
  };
});

vi.mock('../../src/features/crews/hooks', async (importOriginal) => {
  const actual = (await importOriginal()) as typeof import('../../src/features/crews/hooks');

  const agentAsset = {
    id: 'agent-1',
    name: 'Ops Lead',
    description: 'Manager',
    current_version: {
      id: 'agent-v1',
      version_no: 1,
      status: 'published',
      payload: {
        role: 'Ops Lead',
        goal: 'Coordinate launch',
        backstory: 'Runs operations.',
        llm_config_json: { model: 'gpt-4o-mini' },
      },
    },
  } as any;
  const agentAsset2 = {
    ...agentAsset,
    id: 'agent-2',
    name: 'QA Lead',
    description: 'Quality',
    current_version: {
      ...agentAsset.current_version,
      id: 'agent-v2',
      payload: {
        ...agentAsset.current_version.payload,
        role: 'QA Lead',
      },
    },
  } as any;
  const agentAsset3 = {
    ...agentAsset,
    id: 'agent-3',
    name: 'Specialist',
    description: 'Delegation candidate',
    current_version: {
      ...agentAsset.current_version,
      id: 'agent-v3',
      payload: {
        ...agentAsset.current_version.payload,
        role: 'Specialist',
      },
    },
  } as any;

  const taskAsset = {
    id: 'task-1',
    name: 'Validate brief',
    description: 'Check the launch brief',
    current_version: {
      id: 'task-v1',
      version_no: 1,
      status: 'published',
      payload: {
        description: 'Check the launch brief',
        expected_output: 'Validated',
        output_json_schema: null,
      },
    },
  } as any;
  const taskAsset2 = {
    ...taskAsset,
    id: 'task-2',
    name: 'Ship release',
    description: 'Complete release steps',
    current_version: {
      ...taskAsset.current_version,
      id: 'task-v2',
      payload: {
        ...taskAsset.current_version.payload,
        description: 'Complete release steps',
      },
    },
  } as any;
  const taskAsset3 = {
    ...taskAsset,
    id: 'task-3',
    name: 'Report status',
    description: 'Report launch status',
    current_version: {
      ...taskAsset.current_version,
      id: 'task-v3',
      payload: {
        ...taskAsset.current_version.payload,
        description: 'Report launch status',
      },
    },
  } as any;

  function createCompleteCanvasDraft() {
    if (state.draftVariant === 'empty') {
      return {
        selectedNodeId: null,
        nodes: [],
        edges: [],
        insertionOrder: [],
        nodePositions: {},
      };
    }

    if (state.draftVariant === 'placeholder-only') {
      return {
        selectedNodeId: null,
        nodes: [{ nodeId: 'placeholder:1', kind: 'placeholder', insertedAt: 0 }],
        edges: [],
        insertionOrder: ['placeholder:1'],
        nodePositions: {},
      };
    }

    if (state.draftVariant === 'placeholder-with-task') {
      return {
        selectedNodeId: null,
        nodes: [
          { nodeId: 'placeholder:1', kind: 'placeholder', insertedAt: 0 },
          { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'task-v1', insertedAt: 1 },
        ],
        edges: [],
        insertionOrder: ['placeholder:1', 'task:task-1'],
        nodePositions: {},
      };
    }

    if (state.draftVariant === 'missing-agent') {
      return {
        selectedNodeId: null,
        nodes: [{ nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'task-v1', insertedAt: 0 }],
        edges: [],
        insertionOrder: ['task:task-1'],
        nodePositions: {},
      };
    }

    if (state.draftVariant === 'multi-row') {
      return {
        selectedNodeId: null,
        nodes: [
          { nodeId: 'agent:agent-1', kind: 'agent', assetId: 'agent-1', versionId: 'agent-v1', insertedAt: 0 },
          { nodeId: 'agent:agent-2', kind: 'agent', assetId: 'agent-2', versionId: 'agent-v2', insertedAt: 1 },
          { nodeId: 'agent:agent-3', kind: 'agent', assetId: 'agent-3', versionId: 'agent-v3', insertedAt: 2 },
          { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'task-v1', insertedAt: 3 },
          { nodeId: 'task:task-2', kind: 'task', assetId: 'task-2', versionId: 'task-v2', insertedAt: 4 },
          { nodeId: 'task:task-3', kind: 'task', assetId: 'task-3', versionId: 'task-v3', insertedAt: 5 },
        ],
        edges: [
          { id: 'assign:agent-1:task-1', kind: 'agent_assignment', source: 'agent:agent-1', target: 'task:task-1' },
          { id: 'assign:agent-2:task-2', kind: 'agent_assignment', source: 'agent:agent-2', target: 'task:task-2' },
          { id: 'assign:agent-1:task-3', kind: 'agent_assignment', source: 'agent:agent-1', target: 'task:task-3' },
        ],
        insertionOrder: ['agent:agent-1', 'agent:agent-2', 'agent:agent-3', 'task:task-1', 'task:task-2', 'task:task-3'],
        nodePositions: {
          'task:task-2': { x: 320, y: 120 },
        },
      };
    }

    if (state.draftVariant === 'stale-agent') {
      return {
        selectedNodeId: null,
        nodes: [
          { nodeId: 'agent:missing-agent', kind: 'agent', assetId: 'missing-agent', versionId: 'agent-v1', insertedAt: 0 },
          { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'task-v1', insertedAt: 1 },
        ],
        edges: [{ id: 'assign:missing:task-1', kind: 'agent_assignment', source: 'agent:missing-agent', target: 'task:task-1' }],
        insertionOrder: ['agent:missing-agent', 'task:task-1'],
        nodePositions: {},
      };
    }

    return {
      selectedNodeId: null,
      nodes: [
        { nodeId: 'agent:agent-1', kind: 'agent', assetId: 'agent-1', versionId: 'agent-v1', insertedAt: 0 },
        { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'task-v1', insertedAt: 1 },
      ],
      edges: [{ id: 'assign:agent-1:task-1', kind: 'agent_assignment', source: 'agent:agent-1', target: 'task:task-1' }],
      insertionOrder: ['agent:agent-1', 'task:task-1'],
      nodePositions: {},
    };
  }

  return {
    ...actual,
    createEmptyCrewCanvasDraft: createCompleteCanvasDraft,
    createCrewFormValues: (crew?: any) => ({
      name: crew?.name ?? '',
      description: crew?.description ?? '',
      process: crew?.process ?? crew?.processType ?? 'sequential',
      processType: crew?.processType ?? 'sequential',
      managerAgentAssetId: crew?.managerAgentAssetId ?? '',
      managerLlm: crew?.managerLlm ?? crew?.managerLlmModel ?? '',
      managerLlmModel: crew?.managerLlmModel ?? '',
      functionCallingLlm: crew?.functionCallingLlm ?? '',
      verbose: crew?.verbose ?? crew?.isVerbose ?? false,
      planning: crew?.planning ?? false,
      memory: crew?.memory ?? crew?.memoryEnabled ?? false,
      memoryEnabled: crew?.memoryEnabled ?? false,
      cache: crew?.cache ?? false,
      maxRpm: crew?.maxRpm,
      stream: crew?.stream ?? false,
      tracing: crew?.tracing ?? false,
      checkpoint: crew?.checkpoint ?? false,
      outputLogFile: crew?.outputLogFile ?? '',
      planningLlm: crew?.planningLlm ?? '',
      chatLlm: crew?.chatLlm ?? '',
      embedder: crew?.embedder ?? '',
      isVerbose: crew?.isVerbose ?? false,
      canvasDraft: createCompleteCanvasDraft(),
    }),
    useCrewLibrary: () => ({
      crews: [
        {
          assetId: 'crew-1',
          versionId: state.crewVersionId,
          versionNo: 1,
          name: 'Launch Crew',
          description: 'Prepare the launch work and verify delivery.',
          process: state.processType,
          processType: state.processType,
          managerAgentAssetId: '',
          managerAgentName: '',
          managerLlm: 'gpt-4o',
          managerLlmModel: 'gpt-4o',
          functionCallingLlm: '',
          verbose: true,
          planning: true,
          memory: false,
          memoryEnabled: false,
          cache: false,
          maxRpm: undefined,
          stream: false,
          tracing: false,
          checkpoint: false,
          outputLogFile: '',
          planningLlm: '',
          chatLlm: '',
          embedder: '',
          isVerbose: true,
          payload: {
            process: state.processType,
            manager_llm: { provider: 'openai', model: 'gpt-4o', temperature: 0.2 },
            share_crew: true,
            prompt_file: 'crew_prompt.md',
          },
          status: 'draft',
        },
      ],
      availableAgents: [
        { assetId: 'agent-1', versionId: 'agent-v1', name: 'Ops Lead', subtitle: 'Manager', toolKeys: ['web_search'] },
        { assetId: 'agent-2', versionId: 'agent-v2', name: 'QA Lead', subtitle: 'Quality', toolKeys: [] },
        { assetId: 'agent-3', versionId: 'agent-v3', name: 'Specialist', subtitle: 'Delegation candidate', toolKeys: [] },
      ],
      availableTasks: [
        { assetId: 'task-1', versionId: 'task-v1', name: 'Validate brief', subtitle: 'Check the launch brief', toolKeys: [] },
        { assetId: 'task-2', versionId: 'task-v2', name: 'Ship release', subtitle: 'Complete release steps', toolKeys: [] },
        { assetId: 'task-3', versionId: 'task-v3', name: 'Report status', subtitle: 'Report launch status', toolKeys: [] },
      ],
      availableTools: [{ key: 'web_search', name: 'Web Search', description: 'Browse the web' }],
      crewAssetsById: new Map([
        [
          'crew-1',
          {
            id: 'crew-1',
            name: 'Launch Crew',
            description: 'Prepare the launch work and verify delivery.',
            current_version: {
              id: state.crewVersionId,
              version_no: 1,
              status: 'draft',
              payload: {
                process: state.processType,
                manager_agent_asset_id: null,
                manager_llm: { provider: 'openai', model: 'gpt-4o', temperature: 0.2 },
                share_crew: true,
                prompt_file: 'crew_prompt.md',
                payload_json: {},
              },
            },
          } as any,
        ],
      ]),
      agentAssetsById: new Map([
        ['agent-1', agentAsset],
        ['agent-2', agentAsset2],
        ['agent-3', agentAsset3],
      ]),
      taskAssetsById: new Map([
        ['task-1', taskAsset],
        ['task-2', taskAsset2],
        ['task-3', taskAsset3],
      ]),
      toolCatalogByKey: new Map([
        [
          'web_search',
          {
            tool_key: 'web_search',
            name: 'Web Search',
            description: 'Browse the web',
          },
        ],
      ]),
      agentVersionTools: new Map([['agent-v1', ['web_search']]]),
      taskVersionTools: new Map(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }),
    useCreateCrew: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useUpdateCrew: actual.useUpdateCrew,
    useDeleteCrew: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useLoadCrewDraft: () => ({ mutateAsync: loadCrewDraftSpy, isPending: false }),
    useSaveCrewDraft: () => ({ mutateAsync: saveCrewDraftSpy, isPending: false }),
    useValidateCrewDraft: () => ({ mutateAsync: validateCrewDraftSpy, isPending: false }),
    usePublishCrewDraft: () => ({ mutateAsync: publishCrewDraftSpy, isPending: false }),
  };
});

function renderCrewsPage() {
  const queryClient = new QueryClient();

  function makeElement() {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/build/crews']}>
          <CrewsPage />
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  const view = render(makeElement());
  return {
    ...view,
    rerenderApp: () => view.rerender(makeElement()),
  };
}

function deferred<T>() {
  let resolve: (value: T) => void = () => undefined;
  let reject: (reason?: unknown) => void = () => undefined;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });

  return { promise, resolve, reject };
}

beforeEach(() => {
  state.crewVersionId = 'crew-v1';
  state.processType = 'sequential';
  state.draftVariant = 'complete';
  updateAssetSpy.mockReset();
  updateAssetSpy.mockResolvedValue({ data: { id: 'crew-1' } });
  saveCrewDraftSpy.mockReset();
  saveCrewDraftSpy.mockResolvedValue({ draft: { id: 'draft-1' } });
  publishCrewDraftSpy.mockReset();
  publishCrewDraftSpy.mockResolvedValue({ version: { version_no: 2 }, already_published: false });
  loadCrewDraftSpy.mockReset();
  loadCrewDraftSpy.mockResolvedValue(null);
  validateCrewDraftSpy.mockReset();
  validateCrewDraftSpy.mockResolvedValue({ schemaVersion: 1 });
});

test('crew payload mapper returns sparse top-level runtime fields only', () => {
  const values: CrewFormValues = {
    name: 'Runtime Crew',
    description: 'Configure runtime behavior',
    process: 'hierarchical',
    managerAgentAssetId: '',
    managerLlm: 'gpt-4o',
    functionCallingLlm: '',
    verbose: false,
    planning: true,
    memory: false,
    cache: true,
    maxRpm: 30,
    stream: true,
    tracing: false,
    checkpoint: true,
    outputLogFile: '',
    planningLlm: 'gpt-4o-mini',
    chatLlm: '',
    embedder: 'text-embedding-3-small',
    canvasDraft: {
      selectedNodeId: null,
      nodes: [{ nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'task-v1', insertedAt: 0 }],
      edges: [],
      insertionOrder: ['task:task-1'],
      nodePositions: {},
    },
  };

  expect(toCrewAssetPayload(values)).toEqual({
    process: 'hierarchical',
    manager_llm: 'gpt-4o',
    verbose: false,
    planning: true,
    memory: false,
    cache: true,
    max_rpm: 30,
    stream: true,
    tracing: false,
    checkpoint: true,
    planning_llm: 'gpt-4o-mini',
    embedder: { model: 'text-embedding-3-small' },
  });
  expect(toCrewAssetPayload(values)).not.toHaveProperty('manager_agent_asset_id');
  expect(toCrewAssetPayload(values)).not.toHaveProperty('agents');
  expect(toCrewAssetPayload(values)).not.toHaveProperty('tasks');
  expect(toCrewAssetPayload(values)).not.toHaveProperty('canvasDraft');
});

test('crew modal: create and runtime settings open Configure Crew without task or agent attribute fields', async () => {
  renderCrewsPage();

  fireEvent.click(screen.getByRole('button', { name: /\+ new/i }));

  const createDialog = await screen.findByRole('dialog', { name: /configure crew/i });
  expect(screen.getByRole('textbox', { name: /crew name/i })).toBeInTheDocument();
  expect(within(createDialog).queryByLabelText(/^tasks$/i)).not.toBeInTheDocument();
  expect(within(createDialog).queryByLabelText(/^agents$/i)).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
  fireEvent.click(screen.getByRole('button', { name: /launch crew/i }));
  fireEvent.click(await screen.findByRole('button', { name: /runtime settings/i }));

  expect(await screen.findByRole('dialog', { name: /configure crew/i })).toBeInTheDocument();
});

test('crew modal requires manager agent or manager llm for hierarchical crews', async () => {
  renderCrewsPage();

  fireEvent.click(screen.getByRole('button', { name: /\+ new/i }));

  const dialog = await screen.findByRole('dialog', { name: /configure crew/i });
  fireEvent.change(within(dialog).getByRole('textbox', { name: /crew name/i }), {
    target: { value: 'Hierarchical Crew' },
  });
  fireEvent.click(within(dialog).getByRole('button', { name: /hierarchical/i }));

  expect(within(dialog).getByText(/select a manager agent or manager llm/i)).toBeInTheDocument();
  expect(within(dialog).getByRole('button', { name: /save configuration/i })).toBeDisabled();
});

test('crew modal accepts arbitrary runtime model identifiers without hardcoded options', async () => {
  renderCrewsPage();

  fireEvent.click(screen.getByRole('button', { name: /launch crew/i }));
  fireEvent.click(await screen.findByRole('button', { name: /runtime settings/i }));

  const dialog = await screen.findByRole('dialog', { name: /configure crew/i });
  fireEvent.click(within(dialog).getByRole('button', { name: /hierarchical/i }));
  fireEvent.change(within(dialog).getByRole('textbox', { name: /manager llm/i }), {
    target: { value: 'openai/gpt-4.1' },
  });
  fireEvent.click(within(dialog).getByRole('button', { name: /save configuration/i }));

  await waitFor(() => {
    expect(updateAssetSpy).toHaveBeenCalledWith(
      'crew-1',
      expect.objectContaining({
        payload: expect.objectContaining({
          process: 'hierarchical',
          manager_llm: 'openai/gpt-4.1',
        }),
      }),
    );
  });
});

test('crew modal edit persists changed crew name and description in update body', async () => {
  renderCrewsPage();

  fireEvent.click(screen.getByRole('button', { name: /launch crew/i }));
  fireEvent.click(await screen.findByRole('button', { name: /runtime settings/i }));

  const dialog = await screen.findByRole('dialog', { name: /configure crew/i });
  fireEvent.change(within(dialog).getByRole('textbox', { name: /crew name/i }), {
    target: { value: 'Renamed Launch Crew' },
  });
  fireEvent.change(within(dialog).getByRole('textbox', { name: /description/i }), {
    target: { value: 'Updated runtime metadata.' },
  });
  fireEvent.click(within(dialog).getByRole('button', { name: /save configuration/i }));

  await waitFor(() => {
    expect(updateAssetSpy).toHaveBeenCalledWith(
      'crew-1',
      expect.objectContaining({
        base_version_id: 'crew-v1',
        name: 'Renamed Launch Crew',
        description: 'Updated runtime metadata.',
        payload: expect.objectContaining({
          process: 'sequential',
          share_crew: true,
          prompt_file: 'crew_prompt.md',
          manager_llm: { provider: 'openai', model: 'gpt-4o', temperature: 0.2 },
        }),
      }),
    );
  });
});

test('crew graph document rejects stale agent or task ids before emitting dangling edges', () => {
  const crewAsset = {
    id: 'crew-1',
    name: 'Launch Crew',
    description: 'Prepare launch',
    current_version: {
      id: 'crew-v1',
      version_no: 1,
      status: 'draft',
      payload: { process: 'sequential' },
    },
  } as any;
  const taskAsset = {
    id: 'task-1',
    name: 'Validate brief',
    description: 'Check the launch brief',
    current_version: {
      id: 'task-v1',
      version_no: 1,
      status: 'published',
      payload: { description: 'Check the launch brief' },
    },
  } as any;

  expect(() =>
    buildCrewGraphDocument({
      crewAsset,
      draft: {
        selectedNodeId: null,
        nodes: [
          { nodeId: 'agent:missing-agent', kind: 'agent', assetId: 'missing-agent', versionId: 'agent-v1', insertedAt: 0 },
          { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'task-v1', insertedAt: 1 },
        ],
        edges: [{ id: 'assign:missing:task-1', kind: 'agent_assignment', source: 'agent:missing-agent', target: 'task:task-1' }],
        insertionOrder: ['agent:missing-agent', 'task:task-1'],
        nodePositions: {},
      },
      agentAssetsById: new Map(),
      taskAssetsById: new Map([['task-1', taskAsset]]),
      toolCatalogByKey: new Map(),
    }),
  ).toThrow(/agent node references an unknown asset: missing-agent/i);
});

test('crew graph document serializes direct canvas graph nodes, runtime edges, and tools', () => {
  const crewAsset = {
    id: 'crew-1',
    name: 'Launch Crew',
    description: 'Prepare launch',
    current_version: {
      id: 'crew-v1',
      version_no: 1,
      status: 'draft',
      payload: { process: 'sequential' },
    },
  } as any;
  const agentAsset = {
    id: 'agent-1',
    name: 'Ops Lead',
    description: 'Manager',
    current_version: {
      id: 'agent-v1',
      version_no: 1,
      status: 'published',
      payload: { role: 'Ops Lead' },
    },
  } as any;
  const taskAsset = {
    id: 'task-1',
    name: 'Validate brief',
    description: 'Check the launch brief',
    current_version: {
      id: 'task-v1',
      version_no: 1,
      status: 'published',
      payload: { description: 'Check the launch brief' },
    },
  } as any;

  const graph = buildCrewGraphDocument({
    crewAsset,
    draft: {
      selectedNodeId: null,
      nodes: [
        { nodeId: 'agent:agent-1', kind: 'agent', assetId: 'agent-1', versionId: 'agent-v1', insertedAt: 0 },
        { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'task-v1', insertedAt: 1 },
      ],
      edges: [{ id: 'assign:agent-1:task-1', kind: 'agent_assignment', source: 'agent:agent-1', target: 'task:task-1' }],
      insertionOrder: ['agent:agent-1', 'task:task-1'],
      nodePositions: {},
    },
    agentAssetsById: new Map([['agent-1', agentAsset]]),
    taskAssetsById: new Map([['task-1', taskAsset]]),
    toolCatalogByKey: new Map([
      [
        'web_search',
        {
          tool_key: 'web_search',
          name: 'Web Search',
          description: 'Browse the web',
          tool_type: 'local',
          module_path: 'tools.search',
          class_name: 'WebSearchTool',
          default_config_json: {},
        } as any,
      ],
    ]),
    agentVersionTools: new Map([['agent-v1', ['web_search']]]),
  });

  expect(graph.nodes).toEqual(
    expect.arrayContaining([
      expect.objectContaining({ id: 'crew:crew-1', type: 'crew' }),
      expect.objectContaining({ id: 'agent:agent-1', type: 'agent' }),
      expect.objectContaining({ id: 'task:task-1', type: 'task' }),
    ]),
  );
  expect(graph.nodes.some((node: any) => node.type === 'tool')).toBe(false);
  expect(graph.nodes.some((node: any) => node.type === 'step')).toBe(false);
  expect(graph.edges).toEqual(
    expect.arrayContaining([
      expect.objectContaining({ source: 'agent:agent-1', target: 'task:task-1', type: 'agent_assignment' }),
    ]),
  );
  expect(graph.edges.some((edge: any) => edge.type === 'agent_uses_tool' || edge.type === 'task_uses_tool')).toBe(false);
  expect(graph.entities?.tools).toEqual(
    expect.objectContaining({
      web_search: expect.objectContaining({
        tool_key: 'web_search',
        name: 'Web Search',
        description: 'Browse the web',
      }),
    }),
  );
});

test('crew builder: draft save + publish persist the direct canvas graph document', async () => {
  renderCrewsPage();

  fireEvent.click(screen.getByRole('button', { name: /launch crew/i }));

  const publishButton = await screen.findByRole('button', { name: /^publish$/i });
  await waitFor(() => {
    expect(publishButton).not.toBeDisabled();
  });

  fireEvent.click(screen.getByRole('button', { name: /draft save/i }));

  await waitFor(() => {
    const savedGraph = saveCrewDraftSpy.mock.calls.at(-1)?.[0]?.graph;

    expect(savedGraph).toBeTruthy();
    expect(saveCrewDraftSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        crewAssetId: 'crew-1',
        graph: expect.objectContaining({
          schemaVersion: 1,
          nodes: expect.arrayContaining([
            expect.objectContaining({ id: 'crew:crew-1', type: 'crew' }),
            expect.objectContaining({ id: 'agent:agent-1', type: 'agent' }),
            expect.objectContaining({ id: 'task:task-1', type: 'task' }),
          ]),
          edges: expect.arrayContaining([
            expect.objectContaining({ source: 'agent:agent-1', target: 'task:task-1', type: 'agent_assignment' }),
          ]),
        }),
      }),
    );
    expect(savedGraph.nodes.some((node: any) => node.type === 'tool')).toBe(false);
    expect(savedGraph.nodes.some((node: any) => node.type === 'step')).toBe(false);
    expect(savedGraph.edges.some((edge: any) => edge.type === 'step_agent')).toBe(false);
    expect(savedGraph.edges.some((edge: any) => edge.type === 'step_task')).toBe(false);
    expect(savedGraph.edges.some((edge: any) => edge.type === 'agent_uses_tool' || edge.type === 'task_uses_tool')).toBe(false);
  });

  fireEvent.click(screen.getByRole('button', { name: /확인/i }));
  fireEvent.click(screen.getByRole('button', { name: /^publish$/i }));
  expect(await screen.findByRole('dialog', { name: /현재 Crew를 새 버전으로 배포하시겠습니까/i })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /확인/i }));

  await waitFor(() => {
    expect(publishCrewDraftSpy).toHaveBeenCalledWith('crew-1');
  });
});

test('crew builder: shows action feedback for save validation publish and already published', async () => {
  publishCrewDraftSpy.mockResolvedValueOnce({ version: { version_no: 2 }, already_published: true });
  renderCrewsPage();

  fireEvent.click(screen.getByRole('button', { name: /launch crew/i }));

  const saveButton = await screen.findByRole('button', { name: /draft save/i });
  await waitFor(() => expect(saveButton).not.toBeDisabled());

  fireEvent.click(saveButton);
  expect(await screen.findByRole('dialog', { name: /draft saved/i })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /확인/i }));

  fireEvent.click(screen.getByRole('button', { name: /test validation/i }));
  expect(await screen.findByRole('dialog', { name: /test validation completed/i })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /확인/i }));

  fireEvent.click(screen.getByRole('button', { name: /^publish$/i }));
  expect(await screen.findByRole('dialog', { name: /현재 Crew를 새 버전으로 배포하시겠습니까/i })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /확인/i }));
  expect(await screen.findByRole('dialog', { name: /이미 같은 버전이 배포되어 있습니다/i })).toBeInTheDocument();
});

test('crew builder: shows retry dialog when publish fails', async () => {
  publishCrewDraftSpy.mockRejectedValueOnce(new Error('server unavailable'));
  publishCrewDraftSpy.mockResolvedValueOnce({ version: { version_no: 2 }, already_published: false });
  renderCrewsPage();

  fireEvent.click(screen.getByRole('button', { name: /launch crew/i }));

  const publishButton = await screen.findByRole('button', { name: /^publish$/i });
  await waitFor(() => expect(publishButton).not.toBeDisabled());
  fireEvent.click(publishButton);
  expect(await screen.findByRole('dialog', { name: /현재 Crew를 새 버전으로 배포하시겠습니까/i })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /확인/i }));

  expect(await screen.findByRole('dialog', { name: /배포에 실패했습니다/i })).toBeInTheDocument();
  expect(screen.getByText('server unavailable')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /다시 시도/i }));

  await waitFor(() => expect(publishCrewDraftSpy).toHaveBeenCalledTimes(2));
  expect(await screen.findByRole('dialog', { name: /publish completed/i })).toBeInTheDocument();
});

test('crew builder: shows validation failure detail in feedback dialog', async () => {
  validateCrewDraftSpy.mockRejectedValueOnce(new Error('Step 1 must select a Task.'));
  renderCrewsPage();

  fireEvent.click(screen.getByRole('button', { name: /launch crew/i }));

  const validateButton = await screen.findByRole('button', { name: /test validation/i });
  await waitFor(() => expect(validateButton).not.toBeDisabled());

  fireEvent.click(validateButton);

  expect(await screen.findByRole('dialog', { name: /test validation failed/i })).toBeInTheDocument();
  expect(screen.getByText('Step 1 must select a Task.')).toBeInTheDocument();
});

test('crew builder: shows save failure detail in feedback dialog', async () => {
  saveCrewDraftSpy.mockRejectedValueOnce(new Error('Crew graph has a dangling step edge.'));
  renderCrewsPage();

  fireEvent.click(screen.getByRole('button', { name: /launch crew/i }));

  const saveButton = await screen.findByRole('button', { name: /draft save/i });
  await waitFor(() => expect(saveButton).not.toBeDisabled());

  fireEvent.click(saveButton);

  expect(await screen.findByRole('dialog', { name: /draft save failed/i })).toBeInTheDocument();
  expect(screen.getByText('Crew graph has a dangling step edge.')).toBeInTheDocument();
});

test('crew builder: shows validation pending label during draft save phase', async () => {
  const saveDeferred = deferred<{ draft: { id: string } }>();
  saveCrewDraftSpy.mockReturnValueOnce(saveDeferred.promise);
  renderCrewsPage();

  fireEvent.click(screen.getByRole('button', { name: /launch crew/i }));

  const validateButton = await screen.findByRole('button', { name: /test validation/i });
  await waitFor(() => expect(validateButton).not.toBeDisabled());

  fireEvent.click(validateButton);

  expect(await screen.findByRole('button', { name: /validating/i })).toBeDisabled();
  expect(screen.getByRole('button', { name: /draft save/i })).toBeDisabled();

  await act(async () => {
    saveDeferred.resolve({ draft: { id: 'draft-1' } });
  });

  expect(await screen.findByRole('dialog', { name: /test validation completed/i })).toBeInTheDocument();
});

test('crew builder: shows publish pending label during draft save phase', async () => {
  const saveDeferred = deferred<{ draft: { id: string } }>();
  saveCrewDraftSpy.mockReturnValueOnce(saveDeferred.promise);
  renderCrewsPage();

  fireEvent.click(screen.getByRole('button', { name: /launch crew/i }));

  const publishButton = await screen.findByRole('button', { name: /^publish$/i });
  await waitFor(() => expect(publishButton).not.toBeDisabled());

  fireEvent.click(publishButton);
  expect(await screen.findByRole('dialog', { name: /현재 Crew를 새 버전으로 배포하시겠습니까/i })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /확인/i }));

  expect(await screen.findByRole('button', { name: /publishing/i })).toBeDisabled();
  expect(screen.getByRole('button', { name: /draft save/i })).toBeDisabled();

  await act(async () => {
    saveDeferred.resolve({ draft: { id: 'draft-1' } });
  });

  expect(await screen.findByRole('dialog', { name: /publish completed/i })).toBeInTheDocument();
});

test('crew builder: hierarchical crews can validate and publish canvas graphs', async () => {
  state.processType = 'hierarchical';

  renderCrewsPage();

  const crewCard = screen.getByRole('button', { name: /launch crew/i });
  fireEvent.click(crewCard);

  const validateButton = await screen.findByRole('button', { name: /Test Validation/i });
  const publishButton = screen.getByRole('button', { name: /Publish/i });

  await waitFor(() => {
    expect(validateButton).not.toBeDisabled();
    expect(publishButton).not.toBeDisabled();
  });
});

test('crew builder canvas blocks sequential publish until each task has an assigned agent', async () => {
  state.draftVariant = 'missing-agent';
  renderCrewsPage();

  fireEvent.click(screen.getByRole('button', { name: /launch crew/i }));

  const publishButton = await screen.findByRole('button', { name: /^publish$/i });

  expect(publishButton).toBeDisabled();
  expect(screen.getByText(/sequential tasks must have an assigned agent/i)).toBeInTheDocument();
  expect(publishCrewDraftSpy).not.toHaveBeenCalled();
});

test('crew builder allows empty and placeholder-only draft saves but blocks validate and publish', async () => {
  state.draftVariant = 'empty';
  const emptyView = renderCrewsPage();

  fireEvent.click(screen.getByRole('button', { name: /launch crew/i }));

  expect(await screen.findByRole('button', { name: /draft save/i })).not.toBeDisabled();
  expect(screen.getByRole('button', { name: /test validation/i })).toBeDisabled();
  expect(screen.getByRole('button', { name: /^publish$/i })).toBeDisabled();
  expect(screen.getByText(/must include at least one task/i)).toBeInTheDocument();

  emptyView.unmount();

  state.draftVariant = 'placeholder-only';
  renderCrewsPage();

  fireEvent.click(screen.getByRole('button', { name: /launch crew/i }));

  expect(await screen.findByRole('button', { name: /draft save/i })).not.toBeDisabled();
  expect(screen.getByRole('button', { name: /test validation/i })).toBeDisabled();
  expect(screen.getByRole('button', { name: /^publish$/i })).toBeDisabled();
  expect(screen.getByText(/must include at least one task/i)).toBeInTheDocument();
  expect(saveCrewDraftSpy).not.toHaveBeenCalled();
});

test('crew builder allows saving placeholders with a task but blocks validate and publish', async () => {
  state.processType = 'hierarchical';
  state.draftVariant = 'placeholder-with-task';
  renderCrewsPage();

  fireEvent.click(screen.getByRole('button', { name: /launch crew/i }));

  const saveButton = await screen.findByRole('button', { name: /draft save/i });
  const validateButton = screen.getByRole('button', { name: /test validation/i });
  const publishButton = screen.getByRole('button', { name: /^publish$/i });

  expect(saveButton).not.toBeDisabled();
  expect(validateButton).toBeDisabled();
  expect(publishButton).toBeDisabled();
  expect(screen.getByText(/bind or remove placeholder nodes/i)).toBeInTheDocument();
});

test('crew builder blocks actions when a canvas node references an unknown agent', async () => {
  state.draftVariant = 'stale-agent';
  renderCrewsPage();

  fireEvent.click(screen.getByRole('button', { name: /launch crew/i }));

  const publishButton = await screen.findByRole('button', { name: /^publish$/i });

  expect(publishButton).toBeDisabled();
  expect(screen.getByText(/agent node references an unknown agent/i)).toBeInTheDocument();
  expect(publishCrewDraftSpy).not.toHaveBeenCalled();
});

test('crew graph document preserves direct task sequence edges and node positions', () => {
  const crewAsset = {
    id: 'crew-1',
    name: 'Launch Crew',
    description: 'Prepare launch',
    current_version: {
      id: 'crew-v1',
      version_no: 1,
      status: 'draft',
      payload: { process: 'sequential' },
    },
  } as any;
  const taskAsset = {
    id: 'task-1',
    name: 'Validate brief',
    description: 'Check the launch brief',
    current_version: {
      id: 'task-v1',
      version_no: 1,
      status: 'published',
      payload: { description: 'Check the launch brief' },
    },
  } as any;
  const taskAsset2 = {
    ...taskAsset,
    id: 'task-2',
    name: 'Ship release',
    current_version: { ...taskAsset.current_version, id: 'task-v2' },
  } as any;
  const taskAsset3 = {
    ...taskAsset,
    id: 'task-3',
    name: 'Report status',
    current_version: { ...taskAsset.current_version, id: 'task-v3' },
  } as any;

  const graph = buildCrewGraphDocument({
    crewAsset,
    draft: {
      selectedNodeId: null,
      nodes: [
        { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'task-v1', insertedAt: 0 },
        { nodeId: 'task:task-2', kind: 'task', assetId: 'task-2', versionId: 'task-v2', insertedAt: 1 },
        { nodeId: 'task:task-3', kind: 'task', assetId: 'task-3', versionId: 'task-v3', insertedAt: 2 },
      ],
      edges: [
        { id: 'sequence:task-1:task-2', kind: 'task_sequence', source: 'task:task-1', target: 'task:task-2' },
        { id: 'sequence:task-2:task-3', kind: 'task_sequence', source: 'task:task-2', target: 'task:task-3' },
      ],
      insertionOrder: ['task:task-1', 'task:task-2', 'task:task-3'],
      nodePositions: {
        'task:task-2': { x: 320, y: 120 },
      },
    },
    agentAssetsById: new Map(),
    taskAssetsById: new Map([
      ['task-1', taskAsset],
      ['task-2', taskAsset2],
      ['task-3', taskAsset3],
    ]),
    toolCatalogByKey: new Map(),
  });

  expect(graph.edges.filter((edge: any) => edge.type === 'task_sequence')).toEqual([
    expect.objectContaining({ source: 'task:task-1', target: 'task:task-2' }),
    expect.objectContaining({ source: 'task:task-2', target: 'task:task-3' }),
  ]);
  expect(graph.edges.some((edge: any) => edge.type === 'step_next')).toBe(false);
  expect(graph.nodes.find((node: any) => node.id === 'task:task-2')?.position).toEqual({ x: 320, y: 120 });
});

test('crew builder does not render the removed task row editor', async () => {
  state.draftVariant = 'multi-row';
  renderCrewsPage();

  fireEvent.click(screen.getByRole('button', { name: /launch crew/i }));

  expect(await screen.findByTestId('crew-builder-canvas')).toBeInTheDocument();
  expect(screen.queryByText(/task rows/i)).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /add task row/i })).not.toBeInTheDocument();
});

test('crew builder: loads saved drafts, validates drafts, and reloads when crew version changes', async () => {
  const view = renderCrewsPage();

  const crewCard = screen.getByRole('button', { name: /launch crew/i });
  fireEvent.click(crewCard);

  await waitFor(() => {
    expect(loadCrewDraftSpy).toHaveBeenCalledWith('crew-1');
  });

  const validateButton = await screen.findByRole('button', { name: /test validation/i });
  await waitFor(() => {
    expect(validateButton).not.toBeDisabled();
  });

  fireEvent.click(validateButton);

  await waitFor(() => {
    expect(validateCrewDraftSpy).toHaveBeenCalledWith('crew-1');
  });

  state.crewVersionId = 'crew-v2';
  view.rerenderApp();

  await waitFor(() => {
    expect(loadCrewDraftSpy).toHaveBeenCalledTimes(2);
  });
});
