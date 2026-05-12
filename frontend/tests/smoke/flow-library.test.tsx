import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, test, vi } from 'vitest';
import { FlowsLibraryPage } from '../../src/features/flows/FlowsLibraryPage';
import { draftToFlowGraph, flowGraphDocumentToCanvasDraft } from '../../src/features/flows/flowGraphAdapters';

const {
  createFlowSpy,
  updateFlowSpy,
  deleteFlowSpy,
  loadFlowDraftSpy,
  saveFlowDraftSpy,
  validateFlowDraftSpy,
  publishFlowDraftSpy,
  compatibilityDiagnosticsSpy,
  toolMockCallDiagnosticsSpy,
} = vi.hoisted(() => ({
  createFlowSpy: vi.fn().mockResolvedValue({ id: 'flow-created' }),
  updateFlowSpy: vi.fn().mockResolvedValue({ id: 'flow-1' }),
  deleteFlowSpy: vi.fn().mockResolvedValue(undefined),
  loadFlowDraftSpy: vi.fn().mockResolvedValue(null),
  saveFlowDraftSpy: vi.fn().mockResolvedValue({ draft: { id: 'draft-1' } }),
  validateFlowDraftSpy: vi.fn().mockResolvedValue({ schemaVersion: 1 }),
  publishFlowDraftSpy: vi.fn().mockResolvedValue({ version: { id: 'flow-v2' }, already_published: false }),
  compatibilityDiagnosticsSpy: vi.fn().mockResolvedValue({
    mode: 'compatibility',
    status: 'passed',
    provider_calls: 'blocked',
    required_credentials: ['openai'],
    crews: [{ node_id: 'crew:research', build_crew: 'passed', kickoff: 'passed', llm_call: 'passed' }],
  }),
  toolMockCallDiagnosticsSpy: vi.fn().mockResolvedValue({
    mode: 'tool_mock_call',
    status: 'passed',
    tools: [{ tool_key: 'crewai.serper_dev', external_call: 'not_called' }],
  }),
}));

vi.mock('../../src/features/flows/hooks', async (importOriginal) => {
  const actual = (await importOriginal()) as typeof import('../../src/features/flows/hooks');

  return {
    ...actual,
    useFlowLibrary: () => ({
      flows: [
        {
          assetId: 'flow-1',
          versionId: 'flow-v1',
          versionNo: 1,
          name: 'Launch Flow',
          description: 'Launch',
          status: 'draft',
        },
        {
          assetId: 'flow-2',
          versionId: 'flow-v2',
          versionNo: 1,
          name: 'Retain Flow',
          description: 'Retain',
          status: 'draft',
        },
      ],
      flowAssetsById: new Map([
        [
          'flow-1',
          {
            id: 'flow-1',
            type: 'flow',
            name: 'Launch Flow',
            description: 'Launch',
            workspace_id: null,
            created_at: '2026-04-28T00:00:00Z',
            updated_at: '2026-04-28T00:00:00Z',
            current_version: {
              id: 'flow-v1',
              version_no: 1,
              status: 'draft',
              payload: { entry_method: 'run', timeout_seconds: 180, nested_config: { mode: 'careful' } },
              created_at: '2026-04-28T00:00:00Z',
              updated_at: '2026-04-28T00:00:00Z',
            },
          } as any,
        ],
        [
          'flow-2',
          {
            id: 'flow-2',
            type: 'flow',
            name: 'Retain Flow',
            description: 'Retain',
            workspace_id: null,
            created_at: '2026-04-28T00:00:00Z',
            updated_at: '2026-04-28T00:00:00Z',
            current_version: {
              id: 'flow-v2',
              version_no: 1,
              status: 'draft',
              payload: { entry_method: 'run' },
              created_at: '2026-04-28T00:00:00Z',
              updated_at: '2026-04-28T00:00:00Z',
            },
          } as any,
        ],
      ]),
      isLoading: false,
      isError: false,
    }),
    usePublishedCrewsForFlow: () => ({
      publishedCrews: [
        {
          assetId: 'crew-1',
          versionId: 'crew-v1',
          versionNo: 1,
          name: 'Research Crew',
          description: 'Research',
          status: 'published',
          runtimeSnapshot: {
            schemaVersion: 1,
            required_inputs: ['topic'],
            output_schema: { type: 'object', properties: { final_answer: { type: 'string' } } },
          },
        },
        {
          assetId: 'crew-visual',
          versionId: 'visual-v1',
          versionNo: 1,
          name: 'Visual Crew',
          description: 'Visual',
          status: 'published',
          runtimeSnapshot: {
            schemaVersion: 1,
            required_inputs: ['card_news_slides'],
            output_schema: { type: 'raw' },
          },
        },
      ],
      isLoading: false,
    }),
    useLoadFlowDraft: () => ({ mutateAsync: loadFlowDraftSpy, isPending: false }),
    useSaveFlowDraft: () => ({ mutateAsync: saveFlowDraftSpy, isPending: false }),
    useValidateFlowDraft: () => ({ mutateAsync: validateFlowDraftSpy, isPending: false }),
    useFlowCompatibilityDiagnostics: () => ({ mutateAsync: compatibilityDiagnosticsSpy, isPending: false }),
    useFlowToolMockCallDiagnostics: () => ({ mutateAsync: toolMockCallDiagnosticsSpy, isPending: false }),
    usePublishFlowDraft: () => ({ mutateAsync: publishFlowDraftSpy, isPending: false }),
    useCreateFlow: () => ({ mutateAsync: createFlowSpy, isPending: false }),
    useUpdateFlow: () => ({ mutateAsync: updateFlowSpy, isPending: false }),
    useDeleteFlow: () => ({ mutateAsync: deleteFlowSpy, isPending: false }),
  };
});

function renderPage() {
  const queryClient = new QueryClient();

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/build/flows']}>
        <FlowsLibraryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
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

async function addVisualCrewNode() {
  const addCrewButton = await screen.findByRole('button', { name: /^add crew$/i });
  await waitFor(() => expect(addCrewButton).not.toBeDisabled());
  fireEvent.click(addCrewButton);

  const menu = screen.getByRole('menu', { name: /add flow node/i });
  fireEvent.click(within(menu).getByRole('menuitem', { name: /visual crew/i }));
}

beforeEach(() => {
  createFlowSpy.mockReset();
  createFlowSpy.mockResolvedValue({ id: 'flow-created' });
  updateFlowSpy.mockReset();
  updateFlowSpy.mockResolvedValue({ id: 'flow-1' });
  deleteFlowSpy.mockReset();
  deleteFlowSpy.mockResolvedValue(undefined);
  loadFlowDraftSpy.mockReset();
  loadFlowDraftSpy.mockResolvedValue(null);
  saveFlowDraftSpy.mockReset();
  saveFlowDraftSpy.mockResolvedValue({ draft: { id: 'draft-1' } });
  validateFlowDraftSpy.mockReset();
  validateFlowDraftSpy.mockResolvedValue({ schemaVersion: 1 });
  publishFlowDraftSpy.mockReset();
  publishFlowDraftSpy.mockResolvedValue({ version: { id: 'flow-v2' }, already_published: false });
  compatibilityDiagnosticsSpy.mockReset();
  compatibilityDiagnosticsSpy.mockResolvedValue({
    mode: 'compatibility',
    status: 'passed',
    provider_calls: 'blocked',
    required_credentials: ['openai'],
    crews: [{ node_id: 'crew:research', build_crew: 'passed', kickoff: 'passed', llm_call: 'passed' }],
  });
  toolMockCallDiagnosticsSpy.mockReset();
  toolMockCallDiagnosticsSpy.mockResolvedValue({
    mode: 'tool_mock_call',
    status: 'passed',
    tools: [{ tool_key: 'crewai.serper_dev', external_call: 'not_called' }],
  });
});

test('renders canvas-first flow builder with app navigation and top dropdown', async () => {
  renderPage();

  const pageHeading = await screen.findByRole('heading', { name: /flow builder/i });
  expect(pageHeading).toBeInTheDocument();
  const pageHeader = pageHeading.closest('header');
  expect(pageHeader).not.toBeNull();
  const header = within(pageHeader as HTMLElement);

  expect(screen.getByLabelText(/select flow/i)).toBeInTheDocument();
  expect(screen.getByRole('navigation', { name: /build sections/i })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /agents/i })).toHaveAttribute('href', '/build/agents');
  expect(screen.getByRole('link', { name: /crews/i })).toHaveAttribute('href', '/build/crews');
  expect(screen.getByRole('link', { name: /flows/i })).toHaveAttribute('href', '/build/flows');
  expect(await screen.findByLabelText(/flow canvas/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /\+ new flow/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /draft save/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /^test$/i })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /test validation/i })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: /^publish$/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /^edit$/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /^delete$/i })).toBeInTheDocument();
  expect(header.getAllByRole('button').map((button) => button.textContent?.trim())).toEqual([
    '+ New Flow',
    'Edit',
    'Delete',
    'Draft Save',
    'Test',
    'Publish',
  ]);
  expect(header.queryByRole('button', { name: /^add crew$/i })).not.toBeInTheDocument();
});

test('opens Flow Test Console and runs diagnostic actions without outside-click closing', async () => {
  renderPage();

  const testButton = await screen.findByRole('button', { name: /^test$/i });
  testButton.focus();
  fireEvent.click(testButton);

  const dialog = screen.getByRole('dialog', { name: /flow test console/i });
  expect(dialog).toBeInTheDocument();
  expect(dialog).toHaveFocus();
  expect(dialog).toHaveAccessibleName(/flow test console/i);
  fireEvent.mouseDown(document.body);
  expect(screen.getByRole('dialog', { name: /flow test console/i })).toBeInTheDocument();

  fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true });
  expect(within(dialog).getByRole('button', { name: /view diagnostics/i })).toHaveFocus();
  fireEvent.keyDown(dialog, { key: 'Tab' });
  expect(within(dialog).getByRole('button', { name: /^close$/i })).toHaveFocus();

  fireEvent.click(within(dialog).getByRole('button', { name: /validate graph/i }));
  await waitFor(() => expect(validateFlowDraftSpy).toHaveBeenCalledWith('flow-1'));
  expect(await within(dialog).findByText(/schemaVersion/i)).toBeInTheDocument();

  fireEvent.click(within(dialog).getByRole('button', { name: /compatibility test/i }));
  await waitFor(() => expect(compatibilityDiagnosticsSpy).toHaveBeenCalledWith({ flowAssetId: 'flow-1', inputs: {} }));
  expect(await within(dialog).findByText(/provider calls blocked/i)).toBeInTheDocument();

  fireEvent.click(within(dialog).getByRole('button', { name: /tool mock-call check/i }));
  await waitFor(() => expect(toolMockCallDiagnosticsSpy).toHaveBeenCalledWith('flow-1'));
  expect(await within(dialog).findByText(/crewai.serper_dev/i)).toBeInTheDocument();

  fireEvent.click(within(dialog).getByRole('button', { name: /view diagnostics/i }));
  expect(within(dialog).getByText(/raw diagnostics/i)).toBeInTheDocument();

  fireEvent.click(within(dialog).getByRole('button', { name: /^close$/i }));
  expect(screen.queryByRole('dialog', { name: /flow test console/i })).not.toBeInTheDocument();
  expect(testButton).toHaveFocus();
});

test('resets Flow Test Console results on reopen and prevents flow switching while open', async () => {
  renderPage();

  const testButton = await screen.findByRole('button', { name: /^test$/i });
  const flowSelect = screen.getByLabelText(/select flow/i);
  await waitFor(() => expect(testButton).not.toBeDisabled());

  fireEvent.click(testButton);
  let dialog = screen.getByRole('dialog', { name: /flow test console/i });
  expect(flowSelect).toBeDisabled();

  fireEvent.click(within(dialog).getByRole('button', { name: /validate graph/i }));
  expect(await within(dialog).findByText(/schemaVersion/i)).toBeInTheDocument();

  fireEvent.click(within(dialog).getByRole('button', { name: /^close$/i }));
  expect(flowSelect).not.toBeDisabled();

  fireEvent.click(testButton);
  dialog = screen.getByRole('dialog', { name: /flow test console/i });
  expect(within(dialog).queryByText(/schemaVersion/i)).not.toBeInTheDocument();
  expect(within(dialog).getAllByText(/not run/i)).toHaveLength(3);
});

test('flow builder creates a new flow from the header action', async () => {
  renderPage();

  fireEvent.click(await screen.findByRole('button', { name: /\+ new flow/i }));
  fireEvent.change(screen.getByLabelText(/name/i), { target: { value: 'Content Flow' } });
  fireEvent.change(screen.getByLabelText(/summary/i), { target: { value: 'Coordinates content crews.' } });
  fireEvent.click(screen.getByRole('button', { name: /create flow/i }));

  await waitFor(() =>
    expect(createFlowSpy).toHaveBeenCalledWith({
      name: 'Content Flow',
      description: 'Coordinates content crews.',
    }),
  );
});

test('flow builder saves validates and publishes the active draft', async () => {
  renderPage();

  const saveButton = await screen.findByRole('button', { name: /draft save/i });
  await waitFor(() => expect(saveButton).not.toBeDisabled());

  fireEvent.click(saveButton);
  await waitFor(() => expect(saveFlowDraftSpy).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole('button', { name: /확인/i }));

  fireEvent.click(screen.getByRole('button', { name: /^test$/i }));
  const testConsole = screen.getByRole('dialog', { name: /flow test console/i });
  fireEvent.click(within(testConsole).getByRole('button', { name: /validate graph/i }));
  await waitFor(() => expect(validateFlowDraftSpy).toHaveBeenCalledWith('flow-1'));
  expect(saveFlowDraftSpy).toHaveBeenCalledTimes(2);
  fireEvent.click(within(testConsole).getByRole('button', { name: /^close$/i }));

  fireEvent.click(screen.getByRole('button', { name: /^publish$/i }));
  expect(await screen.findByRole('dialog', { name: /현재 Flow를 새 버전으로 배포하시겠습니까/i })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /확인/i }));
  await waitFor(() => expect(publishFlowDraftSpy).toHaveBeenCalledWith('flow-1'));
  expect(saveFlowDraftSpy).toHaveBeenCalledTimes(3);
});

test('flow builder creates a topic input node when adding a crew that requires topic', async () => {
  renderPage();

  const addCrewButton = await screen.findByRole('button', { name: /^add crew$/i });
  await waitFor(() => expect(addCrewButton).not.toBeDisabled());
  fireEvent.click(addCrewButton);
  fireEvent.click(screen.getByRole('menuitem', { name: /research crew/i }));

  fireEvent.click(screen.getByRole('button', { name: /draft save/i }));

  await waitFor(() => expect(saveFlowDraftSpy).toHaveBeenCalledTimes(1));
  const savedGraph = saveFlowDraftSpy.mock.calls[0][0].graph;

  expect(savedGraph.nodes).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        id: 'input:main',
        type: 'input',
        data: {
          fields: [
            {
              name: 'topic',
              type: 'string',
              required: true,
              description: 'Runtime keyword supplied from the Run page.',
            },
          ],
        },
      }),
      expect.objectContaining({
        id: 'crew:crew-1',
        type: 'crew',
      }),
    ]),
  );
});

test('edits a HITL node retry budget without requiring a prompt', async () => {
  const { container } = renderPage();

  const addHitlButton = await screen.findByRole('button', { name: /add hitl/i });
  await waitFor(() => expect(addHitlButton).not.toBeDisabled());
  fireEvent.click(addHitlButton);

  const hitlNode = await waitFor(() => {
    const node = container.querySelector<HTMLElement>('[data-testid^="rf__node-hitl:"]');
    expect(node).not.toBeNull();
    return node as HTMLElement;
  });

  fireEvent.contextMenu(hitlNode, { clientX: 480, clientY: 260 });
  fireEvent.click(screen.getByRole('menuitem', { name: /configure hitl/i }));

  expect(screen.getByRole('dialog', { name: /configure hitl/i })).toBeInTheDocument();
  expect(screen.queryByLabelText(/Review prompt/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/Allowed decisions/i)).not.toBeInTheDocument();
  expect(screen.getByLabelText(/Max retry attempts/i)).toHaveValue(3);

  fireEvent.change(screen.getByLabelText(/Max retry attempts/i), { target: { value: '2' } });
  fireEvent.click(screen.getByRole('button', { name: /save hitl/i }));
  fireEvent.click(screen.getByRole('button', { name: /draft save/i }));

  await waitFor(() => expect(saveFlowDraftSpy).toHaveBeenCalledTimes(1));
  const savedGraph = saveFlowDraftSpy.mock.calls[0][0].graph;
  const hitlGraphNode = savedGraph.nodes.find((node: any) => node.type === 'hitl');

  expect(hitlGraphNode?.data).toEqual({ maxAttempts: 2 });
});

test('flow graph adapters strip legacy HITL review settings', () => {
  const draft = flowGraphDocumentToCanvasDraft({
    schemaVersion: 1,
    nodes: [
      {
        id: 'hitl:review',
        type: 'hitl',
        position: { x: 320, y: 180 },
        data: {
          prompt: 'Please review this output.',
          allowedDecisions: ['approved', 'needs_revision', 'rejected'],
          onNeedsRevision: 'continue_with_feedback',
          feedbackPropagation: 'all_decisions',
          maxAttempts: 2,
        },
      },
    ],
    edges: [],
  });

  expect(draft.nodes[0]?.data).toEqual({ maxAttempts: 2 });

  const graph = draftToFlowGraph({
    draft: {
      ...draft,
      nodes: [
        {
          ...draft.nodes[0],
          data: {
            ...draft.nodes[0]?.data,
            prompt: 'Legacy prompt',
            allowedDecisions: ['approved'],
            onNeedsRevision: 'retry_previous',
            feedbackPropagation: 'needs_revision_only',
          },
        },
      ],
    },
    publishedCrews: [],
  });

  expect(graph.nodes[0]?.data).toEqual({ maxAttempts: 2 });
});

test('flow builder warns about unresolved crew inputs before saving and can save anyway', async () => {
  renderPage();

  await addVisualCrewNode();

  fireEvent.click(screen.getByRole('button', { name: /draft save/i }));

  expect(await screen.findByRole('dialog', { name: /unresolved flow inputs/i })).toBeInTheDocument();
  expect(screen.getByText('Visual Crew.card_news_slides')).toBeInTheDocument();
  expect(saveFlowDraftSpy).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('button', { name: /save draft anyway/i }));

  await waitFor(() => expect(saveFlowDraftSpy).toHaveBeenCalledTimes(1));
});

test('flow builder test console saves before validating with unresolved crew inputs', async () => {
  renderPage();

  await addVisualCrewNode();

  fireEvent.click(screen.getByRole('button', { name: /^test$/i }));
  const testConsole = screen.getByRole('dialog', { name: /flow test console/i });
  fireEvent.click(within(testConsole).getByRole('button', { name: /validate graph/i }));

  await waitFor(() => expect(saveFlowDraftSpy).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(validateFlowDraftSpy).toHaveBeenCalledWith('flow-1'));
  expect(screen.queryByRole('dialog', { name: /unresolved flow inputs/i })).not.toBeInTheDocument();
});

test('flow builder blocks publish before confirmation when unresolved crew inputs remain', async () => {
  renderPage();

  await addVisualCrewNode();

  fireEvent.click(screen.getByRole('button', { name: /^publish$/i }));

  expect(await screen.findByRole('dialog', { name: /unresolved flow inputs/i })).toBeInTheDocument();
  expect(screen.getByText('Visual Crew.card_news_slides')).toBeInTheDocument();
  expect(screen.queryByRole('dialog', { name: /현재 Flow를 새 버전으로 배포하시겠습니까/i })).not.toBeInTheDocument();
  expect(publishFlowDraftSpy).not.toHaveBeenCalled();
});

test('flow builder shows action feedback for save publish and already published', async () => {
  publishFlowDraftSpy.mockResolvedValueOnce({ version: { id: 'flow-v2' }, already_published: true });
  renderPage();

  const saveButton = await screen.findByRole('button', { name: /draft save/i });
  await waitFor(() => expect(saveButton).not.toBeDisabled());

  fireEvent.click(saveButton);
  expect(await screen.findByRole('dialog', { name: /draft saved/i })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /확인/i }));

  fireEvent.click(screen.getByRole('button', { name: /^test$/i }));
  const testConsole = screen.getByRole('dialog', { name: /flow test console/i });
  fireEvent.click(within(testConsole).getByRole('button', { name: /validate graph/i }));
  expect(await within(testConsole).findByText(/schemaVersion/i)).toBeInTheDocument();
  fireEvent.click(within(testConsole).getByRole('button', { name: /^close$/i }));

  fireEvent.click(screen.getByRole('button', { name: /^publish$/i }));
  expect(await screen.findByRole('dialog', { name: /현재 Flow를 새 버전으로 배포하시겠습니까/i })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /확인/i }));
  expect(await screen.findByRole('dialog', { name: /이미 같은 버전이 배포되어 있습니다/i })).toBeInTheDocument();
});

test('flow builder shows retry dialog when publish fails', async () => {
  publishFlowDraftSpy.mockRejectedValueOnce(new Error('server unavailable'));
  publishFlowDraftSpy.mockResolvedValueOnce({ version: { id: 'flow-v2' }, already_published: false });
  renderPage();

  const publishButton = await screen.findByRole('button', { name: /^publish$/i });
  await waitFor(() => expect(publishButton).not.toBeDisabled());
  fireEvent.click(publishButton);
  expect(await screen.findByRole('dialog', { name: /현재 Flow를 새 버전으로 배포하시겠습니까/i })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /확인/i }));

  expect(await screen.findByRole('dialog', { name: /배포에 실패했습니다/i })).toBeInTheDocument();
  expect(screen.getByText('server unavailable')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /다시 시도/i }));

  await waitFor(() => expect(publishFlowDraftSpy).toHaveBeenCalledTimes(2));
  expect(await screen.findByRole('dialog', { name: /publish completed/i })).toBeInTheDocument();
});

test('flow builder shows validation failure detail in test console', async () => {
  validateFlowDraftSpy.mockRejectedValueOnce(new Error('Crew node is missing required input mapping.'));
  renderPage();

  const testButton = await screen.findByRole('button', { name: /^test$/i });
  await waitFor(() => expect(testButton).not.toBeDisabled());

  fireEvent.click(testButton);
  const testConsole = screen.getByRole('dialog', { name: /flow test console/i });
  fireEvent.click(within(testConsole).getByRole('button', { name: /validate graph/i }));

  expect(await within(testConsole).findByText('Crew node is missing required input mapping.')).toBeInTheDocument();
});

test('flow builder shows save failure detail in feedback dialog', async () => {
  saveFlowDraftSpy.mockRejectedValueOnce(new Error('Draft graph contains a disconnected output node.'));
  renderPage();

  const saveButton = await screen.findByRole('button', { name: /draft save/i });
  await waitFor(() => expect(saveButton).not.toBeDisabled());

  fireEvent.click(saveButton);

  expect(await screen.findByRole('dialog', { name: /draft save failed/i })).toBeInTheDocument();
  expect(screen.getByText('Draft graph contains a disconnected output node.')).toBeInTheDocument();
});

test('flow builder shows validation pending label during draft save phase', async () => {
  const saveDeferred = deferred<{ draft: { id: string } }>();
  saveFlowDraftSpy.mockReturnValueOnce(saveDeferred.promise);
  renderPage();

  const testButton = await screen.findByRole('button', { name: /^test$/i });
  await waitFor(() => expect(testButton).not.toBeDisabled());

  fireEvent.click(testButton);
  const testConsole = screen.getByRole('dialog', { name: /flow test console/i });
  fireEvent.click(within(testConsole).getByRole('button', { name: /validate graph/i }));

  expect(await within(testConsole).findByRole('button', { name: /validate graph/i })).toBeDisabled();
  expect(screen.getByRole('button', { name: /draft save/i })).toBeDisabled();

  await act(async () => {
    saveDeferred.resolve({ draft: { id: 'draft-1' } });
  });

  expect(await within(testConsole).findByText(/schemaVersion/i)).toBeInTheDocument();
});

test('flow builder shows publish pending label during draft save phase', async () => {
  const saveDeferred = deferred<{ draft: { id: string } }>();
  saveFlowDraftSpy.mockReturnValueOnce(saveDeferred.promise);
  renderPage();

  const publishButton = await screen.findByRole('button', { name: /^publish$/i });
  await waitFor(() => expect(publishButton).not.toBeDisabled());

  fireEvent.click(publishButton);
  expect(await screen.findByRole('dialog', { name: /현재 Flow를 새 버전으로 배포하시겠습니까/i })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /확인/i }));

  expect(await screen.findByRole('button', { name: /publishing/i })).toBeDisabled();
  expect(screen.getByRole('button', { name: /draft save/i })).toBeDisabled();

  await act(async () => {
    saveDeferred.resolve({ draft: { id: 'draft-1' } });
  });

  expect(await screen.findByRole('dialog', { name: /publish completed/i })).toBeInTheDocument();
});

test('flow builder disables draft actions until the active draft load resolves', async () => {
  let resolveDraftLoad: (value: null) => void = () => undefined;
  loadFlowDraftSpy.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolveDraftLoad = resolve;
      }),
  );

  renderPage();

  const saveButton = await screen.findByRole('button', { name: /draft save/i });
  expect(saveButton).toBeDisabled();
  expect(screen.getByRole('button', { name: /^edit$/i })).not.toBeDisabled();
  expect(screen.getByRole('button', { name: /^delete$/i })).not.toBeDisabled();
  expect(screen.getByText(/preparing the saved draft/i)).toBeInTheDocument();

  fireEvent.click(saveButton);
  expect(saveFlowDraftSpy).not.toHaveBeenCalled();

  await act(async () => {
    resolveDraftLoad(null);
  });

  await waitFor(() => expect(saveButton).not.toBeDisabled());
  fireEvent.click(saveButton);
  await waitFor(() => expect(saveFlowDraftSpy).toHaveBeenCalledTimes(1));
});

test('flow builder clears a stale draft load after switching away and back', async () => {
  let resolveFirstDraftLoad: (value: null) => void = () => undefined;

  loadFlowDraftSpy.mockImplementation((flowAssetId: string) => {
    if (flowAssetId === 'flow-1') {
      return new Promise((resolve) => {
        resolveFirstDraftLoad = resolve;
      });
    }

    return Promise.resolve(null);
  });

  renderPage();

  const saveButton = await screen.findByRole('button', { name: /draft save/i });
  expect(saveButton).toBeDisabled();

  fireEvent.change(screen.getByLabelText(/select flow/i), { target: { value: 'flow-2' } });
  await waitFor(() => expect(saveButton).not.toBeDisabled());

  await act(async () => {
    resolveFirstDraftLoad(null);
  });

  fireEvent.change(screen.getByLabelText(/select flow/i), { target: { value: 'flow-1' } });

  await waitFor(() => expect(saveButton).not.toBeDisabled());
});

test('flow builder edits active flow metadata without changing payload shape', async () => {
  renderPage();

  const editButton = await screen.findByRole('button', { name: /^edit$/i });
  await waitFor(() => expect(editButton).not.toBeDisabled());

  fireEvent.click(editButton);
  expect(screen.getByRole('dialog', { name: /edit flow/i })).toBeInTheDocument();
  expect(screen.getByLabelText(/name/i)).toHaveValue('Launch Flow');
  expect(screen.getByLabelText(/summary/i)).toHaveValue('Launch');

  fireEvent.change(screen.getByLabelText(/name/i), { target: { value: 'Launch Flow Edited' } });
  fireEvent.change(screen.getByLabelText(/summary/i), { target: { value: 'Edited launch summary.' } });
  fireEvent.click(screen.getByRole('button', { name: /save changes/i }));

  await waitFor(() =>
    expect(updateFlowSpy).toHaveBeenCalledWith({
      assetId: 'flow-1',
      baseVersionId: 'flow-v1',
      name: 'Launch Flow Edited',
      description: 'Edited launch summary.',
      payload: { entry_method: 'run', timeout_seconds: 180, nested_config: { mode: 'careful' } },
    }),
  );
});

test('flow builder shows feedback when metadata update fails', async () => {
  updateFlowSpy.mockRejectedValueOnce(new Error('metadata write failed'));
  renderPage();

  const editButton = await screen.findByRole('button', { name: /^edit$/i });
  await waitFor(() => expect(editButton).not.toBeDisabled());

  fireEvent.click(editButton);
  fireEvent.change(screen.getByLabelText(/name/i), { target: { value: 'Launch Flow Edited' } });
  fireEvent.click(screen.getByRole('button', { name: /save changes/i }));

  expect(await screen.findByRole('dialog', { name: /flow update failed/i })).toBeInTheDocument();
  expect(screen.getByText('metadata write failed')).toBeInTheDocument();
});

test('flow builder deletes the active flow after confirmation', async () => {
  renderPage();

  const deleteButton = await screen.findByRole('button', { name: /^delete$/i });
  await waitFor(() => expect(deleteButton).not.toBeDisabled());

  fireEvent.click(deleteButton);
  expect(screen.getByRole('dialog', { name: /delete flow/i })).toBeInTheDocument();
  expect(screen.getByText(/delete launch flow/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /confirm delete/i }));

  await waitFor(() => expect(deleteFlowSpy).toHaveBeenCalledWith('flow-1'));
});

test('flow builder shows feedback when delete fails', async () => {
  deleteFlowSpy.mockRejectedValueOnce(new Error('delete write failed'));
  renderPage();

  const deleteButton = await screen.findByRole('button', { name: /^delete$/i });
  await waitFor(() => expect(deleteButton).not.toBeDisabled());

  fireEvent.click(deleteButton);
  fireEvent.click(screen.getByRole('button', { name: /confirm delete/i }));

  expect(await screen.findByRole('dialog', { name: /flow delete failed/i })).toBeInTheDocument();
  expect(screen.getByText('delete write failed')).toBeInTheDocument();
});
