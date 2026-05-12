import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';
import { beforeEach, vi } from 'vitest';
import { appRoutes } from '../../src/app/routes';

const runHookMocks = vi.hoisted(() => ({
  selectedRunId: null as string | null,
  createRunSpy: vi.fn(),
  writeSelectedRunIdSpy: vi.fn(),
  submitFeedbackSpy: vi.fn(),
  usePublishedFlowOptions: vi.fn(),
  useCreateFlowRunMutation: vi.fn(),
  useFlowRunDetail: vi.fn(),
  useFlowRunEvents: vi.fn(),
  useSubmitHumanFeedbackMutation: vi.fn(),
}));

vi.mock('../../src/features/runs/hooks', () => ({
  readSelectedRunId: () => runHookMocks.selectedRunId,
  writeSelectedRunId: (runId: string) => {
    runHookMocks.selectedRunId = runId;
    runHookMocks.writeSelectedRunIdSpy(runId);
  },
  usePublishedFlowOptions: runHookMocks.usePublishedFlowOptions,
  useCreateFlowRunMutation: runHookMocks.useCreateFlowRunMutation,
  useFlowRunDetail: runHookMocks.useFlowRunDetail,
  useFlowRunEvents: runHookMocks.useFlowRunEvents,
  useSubmitHumanFeedbackMutation: runHookMocks.useSubmitHumanFeedbackMutation,
}));

function renderAtPath(pathname: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [pathname] });
  render(<RouterProvider router={router} />);
  return router;
}

function makePendingHitlRequest(overrides: Record<string, unknown> = {}) {
  return Object.assign(
    {
      id: 'hfr_123',
      run_id: 'run-123',
      node_id: 'hitl:review',
      status: 'pending',
      prompt_json: {
        message: 'HITL이 실행되었습니다. 계속 진행하시겠습니까?',
        source_node_id: 'crew:content',
        next_node_id: 'crew:visual',
        retry_count: 0,
        max_attempts: 3,
        remaining_retries: 3,
        preview_payload: { raw: 'content output v1' },
      },
      response_json: {},
      created_at: '2026-04-29T00:00:00Z',
      responded_at: null,
      attempt_number: 1,
      expires_at: null,
      resolved_by: null,
      idempotency_key: null,
    },
    overrides,
  );
}

function mockRunDetail(runOverrides: Record<string, unknown>) {
  const refetch = vi.fn();
  runHookMocks.selectedRunId = 'run-123';
  runHookMocks.useFlowRunDetail.mockReturnValue({
    run: Object.assign(
      {
        id: 'run-123',
        status: 'waiting_for_human',
        input_json: { topic: 'AI orchestration' },
        output_json: null,
        latest_state_snapshot: null,
      },
      runOverrides,
    ),
    isLoading: false,
    error: null,
    refetch,
  });
  return refetch;
}

function mockHumanFeedbackSubmit() {
  runHookMocks.submitFeedbackSpy.mockResolvedValue({ id: 'run-123', status: 'running' });
  return runHookMocks.submitFeedbackSpy;
}

class FakeWebSocket {
  static OPEN = 1;
  static instances: FakeWebSocket[] = [];
  url: string;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onopen: (() => void) | null = null;
  sentMessages: string[] = [];

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  close() {
    return undefined;
  }

  send(message: string) {
    this.sentMessages.push(message);
  }

  emitMessage(payload: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
  }
}

beforeEach(() => {
  runHookMocks.selectedRunId = null;
  runHookMocks.createRunSpy.mockReset();
  runHookMocks.createRunSpy.mockResolvedValue({ id: 'run-created' });
  runHookMocks.writeSelectedRunIdSpy.mockReset();
  runHookMocks.submitFeedbackSpy.mockReset();
  runHookMocks.usePublishedFlowOptions.mockReturnValue({
    flows: [
      {
        assetId: 'flow-1',
        versionId: 'flow-version-1',
        name: 'Launch Flow',
        description: 'Launch summary',
        versionNo: 3,
        hasInputNode: true,
      },
    ],
    isLoading: false,
    error: null,
  });
  runHookMocks.useCreateFlowRunMutation.mockReturnValue({
    mutateAsync: runHookMocks.createRunSpy,
    isPending: false,
    error: null,
  });
  runHookMocks.useFlowRunDetail.mockReturnValue({
    run: null,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  });
  runHookMocks.useFlowRunEvents.mockReturnValue({
    events: [],
    isLoading: false,
    error: null,
  });
  runHookMocks.useSubmitHumanFeedbackMutation.mockReturnValue({
    mutateAsync: runHookMocks.submitFeedbackSpy,
    isPending: false,
    error: null,
  });
  window.localStorage.clear();
  window.localStorage.setItem('ai-oh.auth-token', 'smoke-token');
  FakeWebSocket.instances = [];
  vi.stubGlobal('WebSocket', FakeWebSocket);
});

test('I/O page defaults to output preview without a raw json tab', () => {
  runHookMocks.selectedRunId = 'run-123';
  runHookMocks.useFlowRunDetail.mockReturnValue({
    run: {
      id: 'run-123',
      status: 'completed',
      input_json: { topic: 'runtime smoke' },
      output_json: { final_answer: 'Runtime output' },
      latest_state_snapshot: { state_json: { step: 'complete' } },
    },
    isLoading: false,
    error: null,
  });

  renderAtPath('/run/io');

  expect(screen.getByRole('heading', { name: /^i\/o$/i })).toBeInTheDocument();
  expect(screen.getByRole('tablist', { name: /run i\/o views/i })).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: /output preview/i })).toHaveAttribute('aria-selected', 'true');
  expect(screen.getAllByText(/runtime output/i).length).toBeGreaterThan(0);
  expect(screen.queryByText(/"final_answer"/i)).not.toBeInTheDocument();
  expect(screen.queryByRole('tab', { name: /raw json/i })).not.toBeInTheDocument();
  expect(screen.queryByText(/final_answer/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/launch or select a run/i)).not.toBeInTheDocument();
});

test('renders launch controls and starts a run with keyword input when the flow has an input node', async () => {
  renderAtPath('/run');

  expect(screen.getByRole('heading', { name: /^run$/i })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: /published workflow/i })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: /no run selected/i })).toBeInTheDocument();
  expect(screen.getByRole('combobox', { name: /workflow/i })).toHaveDisplayValue('Launch Flow v3');
  expect(screen.getByRole('textbox', { name: /키워드/i })).toBeEnabled();
  expect(screen.getByRole('checkbox', { name: /에이전트 실행 로그 캡처/i })).toBeChecked();

  fireEvent.change(screen.getByRole('textbox', { name: /키워드/i }), {
    target: { value: 'smoke launch' },
  });
  fireEvent.click(screen.getByRole('button', { name: /launch run/i }));

  await waitFor(() =>
    expect(runHookMocks.createRunSpy).toHaveBeenCalledWith({
      flow_version_id: 'flow-version-1',
      inputs: { topic: 'smoke launch' },
      capture_agent_execution_logs: true,
    }),
  );
  expect(runHookMocks.writeSelectedRunIdSpy).toHaveBeenCalledWith('run-created');
});

test('home flow start opens a stage popup and launches with input node keyword', async () => {
  renderAtPath('/home');

  fireEvent.click(screen.getByRole('button', { name: /start flow/i }));

  expect(screen.getByRole('dialog', { name: /업무 의뢰서/i })).toBeInTheDocument();
  expect(screen.getByText(/Launch Flow v3/i)).toBeInTheDocument();
  expect(screen.getByText(/Launch summary/i)).toBeInTheDocument();

  fireEvent.change(screen.getByRole('textbox', { name: /키워드/i }), {
    target: { value: 'home launch topic' },
  });
  fireEvent.click(screen.getByRole('button', { name: /시작하기/i }));

  await waitFor(() =>
    expect(runHookMocks.createRunSpy).toHaveBeenCalledWith({
      flow_version_id: 'flow-version-1',
      inputs: { topic: 'home launch topic' },
      capture_agent_execution_logs: true,
    }),
  );
  expect(runHookMocks.writeSelectedRunIdSpy).toHaveBeenCalledWith('run-created');
});

test('can launch a keyword run with agent execution log capture disabled', async () => {
  renderAtPath('/run');

  fireEvent.change(screen.getByRole('textbox', { name: /키워드/i }), {
    target: { value: 'AI orchestration' },
  });
  fireEvent.click(screen.getByRole('checkbox', { name: /에이전트 실행 로그 캡처/i }));
  fireEvent.click(screen.getByRole('button', { name: /launch run/i }));

  await waitFor(() =>
    expect(runHookMocks.createRunSpy).toHaveBeenCalledWith({
      flow_version_id: 'flow-version-1',
      inputs: { topic: 'AI orchestration' },
      capture_agent_execution_logs: false,
    }),
  );
});

test('renders live run output preview without raw inspect details', () => {
  runHookMocks.selectedRunId = 'run-123';
  runHookMocks.useFlowRunDetail.mockReturnValue({
    run: {
      id: 'run-123',
      status: 'completed',
      input_json: { topic: 'AI orchestration' },
      output_json: {},
      latest_state_snapshot: {
        state_json: {
          node_outputs: {
            'crew:research': { raw: 'early-runtime-validation' },
            'crew:writer': { final_answer: 'latest-runtime-validation' },
          },
        },
      },
    },
    isLoading: false,
    error: null,
  });

  renderAtPath('/run');

  expect(screen.queryByText(/^validation run$/i)).not.toBeInTheDocument();
  expect(screen.getAllByText(/latest-runtime-validation/i).length).toBeGreaterThan(0);
  expect(screen.queryByText(/early-runtime-validation/i)).not.toBeInTheDocument();
  expect(screen.queryByRole('tab', { name: /inspect/i })).not.toBeInTheDocument();
  expect(screen.queryByText(/node_outputs/i)).not.toBeInTheDocument();
});

test('keeps Run page on output preview after launching a new run', async () => {
  runHookMocks.selectedRunId = 'run-123';
  runHookMocks.useFlowRunDetail.mockImplementation((runId: string | null) => ({
    run: runId
      ? {
          id: runId,
          status: 'completed',
          input_json: { topic: 'AI orchestration' },
          output_json: { final_answer: `${runId} output` },
          latest_state_snapshot: null,
        }
      : null,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }));

  renderAtPath('/run');

  fireEvent.click(screen.getByRole('button', { name: /launch run/i }));

  await waitFor(() => expect(screen.queryByRole('tab', { name: /inspect/i })).not.toBeInTheDocument());
  expect(screen.getAllByText(/run-created output/i).length).toBeGreaterThan(0);
});

test('renders image output preview on the Run page without raw inspect json', () => {
  const b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=';
  runHookMocks.selectedRunId = 'run-123';
  runHookMocks.useFlowRunDetail.mockReturnValue({
    run: {
      id: 'run-123',
      status: 'completed',
      input_json: { topic: 'AI image' },
      output_json: { b64_json: b64, revised_prompt: 'A card news image' },
      latest_state_snapshot: null,
    },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  });

  renderAtPath('/run');

  expect(screen.getByRole('img', { name: /a card news image/i })).toHaveAttribute('src', `data:image/png;base64,${b64}`);
  expect(screen.queryByRole('tab', { name: /inspect/i })).not.toBeInTheDocument();
  expect(screen.queryByText(/base64 image truncated/i)).not.toBeInTheDocument();
});

test('renders Nano Banana image generation progress on the Run page', () => {
  runHookMocks.selectedRunId = 'run-123';
  runHookMocks.useFlowRunDetail.mockReturnValue({
    run: {
      id: 'run-123',
      status: 'running',
      input_json: { topic: 'AI image' },
      output_json: null,
      latest_state_snapshot: null,
    },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  });
  runHookMocks.useFlowRunEvents.mockReturnValue({
    events: [
      {
        id: 'nano-start-1',
        event_type: 'image_generation_started',
        created_at: '2026-05-04T12:00:00Z',
        node_id: 'crew:visual',
        event_payload_json: {
          tool: 'nano_banana',
          prompt_preview: 'A launch card image',
        },
      },
      {
        id: 'nano-complete-1',
        event_type: 'image_generation_completed',
        created_at: '2026-05-04T12:00:10Z',
        node_id: 'crew:visual',
        event_payload_json: {
          image_generation: true,
          artifact_id: 'artifact-run-1',
          preview_url: '/api/run-artifacts/artifact-run-1/content',
        },
      },
    ],
    isLoading: false,
    error: null,
  });

  renderAtPath('/run');

  expect(screen.getByRole('heading', { name: /image generation progress/i })).toBeInTheDocument();
  expect(screen.getByText(/crew:visual/i)).toBeInTheDocument();
  expect(screen.getByText(/1 \/ 3 images complete/i)).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: /slide 1/i })).toBeInTheDocument();
  expect(screen.getByText(/artifact-run-1/i)).toBeInTheDocument();
});

test('renders run artifacts even when final output only contains text', async () => {
  const createObjectUrl = vi.fn().mockReturnValue('blob:run-artifact-preview');
  Object.defineProperty(URL, 'createObjectURL', {
    configurable: true,
    value: createObjectUrl,
  });
  Object.defineProperty(URL, 'revokeObjectURL', {
    configurable: true,
    value: vi.fn(),
  });
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      blob: () => Promise.resolve(new Blob(['image-bytes'], { type: 'image/jpeg' })),
    }),
  );
  runHookMocks.selectedRunId = 'run-123';
  runHookMocks.useFlowRunDetail.mockReturnValue({
    run: {
      id: 'run-123',
      status: 'completed',
      input_json: { topic: '항공모함' },
      output_json: {
        raw: 'URL to the generated image: [Download Image](https://api.run-artifacts/artifact-1/content)',
      },
      artifacts: [
        {
          id: 'artifact-1',
          artifact_id: 'artifact-1',
          artifact_type: 'image',
          preview_url: '/api/run-artifacts/artifact-1/content',
          prompt: 'Generated aircraft carrier image',
        },
      ],
      latest_state_snapshot: null,
    },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  });

  renderAtPath('/run');

  const image = await screen.findByRole('img', { name: /generated aircraft carrier image/i });
  expect(image).toHaveAttribute('src', 'blob:run-artifact-preview');
  expect(screen.getByText(/URL to the generated image/i)).toBeInTheDocument();
  vi.unstubAllGlobals();
});

test('shows failed run error details above validation fallback output', () => {
  runHookMocks.selectedRunId = 'run-123';
  runHookMocks.useFlowRunDetail.mockReturnValue({
    run: {
      id: 'run-123',
      status: 'failed',
      input_json: { topic: 'AI orchestration' },
      output_json: {},
      error_message: 'TaskOutput json_dict must be a dictionary',
      latest_state_snapshot: {
        state_json: {
          node_outputs: {
            'crew:writer': { raw: 'latest-runtime-validation' },
          },
        },
      },
    },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  });

  renderAtPath('/run');

  expect(screen.getByText(/taskoutput json_dict must be a dictionary/i)).toBeInTheDocument();
  expect(screen.getAllByText(/latest-runtime-validation/i).length).toBeGreaterThan(0);
});

test('does not open a run event WebSocket for terminal run states', () => {
  mockRunDetail({
    status: 'failed',
    pending_human_feedback_request: null,
  });

  renderAtPath('/run');

  expect(FakeWebSocket.instances).toHaveLength(0);
});

test('uses non-empty output JSON before validation node fallback', () => {
  runHookMocks.selectedRunId = 'run-123';
  runHookMocks.useFlowRunDetail.mockReturnValue({
    run: {
      id: 'run-123',
      status: 'completed',
      input_json: { topic: 'AI orchestration' },
      output_json: { raw: 'output-json-validation' },
      latest_state_snapshot: {
        state_json: {
          node_outputs: {
            'crew:writer': { raw: 'node-output-validation' },
          },
        },
      },
    },
    isLoading: false,
    error: null,
  });

  renderAtPath('/run');

  expect(screen.getAllByText(/output-json-validation/i).length).toBeGreaterThan(0);
  expect(screen.queryByText(/node-output-validation/i)).not.toBeInTheDocument();
});

test('shows the HITL modal from persisted pending request detail', () => {
  mockRunDetail({
    pending_human_feedback_request: makePendingHitlRequest(),
  });

  renderAtPath('/run');

  const dialog = screen.getByRole('dialog');
  expect(dialog).toBeInTheDocument();
  expect(dialog).toHaveFocus();
  expect(screen.getByText('HITL이 실행되었습니다. 계속 진행하시겠습니까?')).toBeInTheDocument();
  expect(screen.getByRole('textbox', { name: /^feedback$/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '승인' })).toBeEnabled();
  expect(screen.getByRole('button', { name: '거절' })).toBeEnabled();
  expect(screen.getByRole('button', { name: '재시도' })).toBeEnabled();
  expect(screen.getByText(/content output v1/i)).toBeInTheDocument();
});

test('submits approve with feedback to the backend', async () => {
  mockRunDetail({
    pending_human_feedback_request: makePendingHitlRequest(),
  });
  const submitFeedback = mockHumanFeedbackSubmit();

  renderAtPath('/run');

  fireEvent.change(screen.getByRole('textbox', { name: /^feedback$/i }), {
    target: { value: 'Looks good' },
  });
  fireEvent.click(screen.getByRole('button', { name: '승인' }));

  await waitFor(() =>
    expect(submitFeedback).toHaveBeenCalledWith(
      expect.objectContaining({
        request_id: 'hfr_123',
        outcome: 'approved',
        feedback: 'Looks good',
        idempotency_key: 'human-feedback:hfr_123:approved',
      }),
    ),
  );
});

test('keeps the HITL idempotency key stable across submit retries for the same request and outcome', async () => {
  mockRunDetail({
    pending_human_feedback_request: makePendingHitlRequest(),
  });
  const submitFeedback = mockHumanFeedbackSubmit();

  renderAtPath('/run');

  fireEvent.change(screen.getByRole('textbox', { name: /^feedback$/i }), {
    target: { value: 'Looks good' },
  });
  fireEvent.click(screen.getByRole('button', { name: '승인' }));

  await waitFor(() => expect(submitFeedback).toHaveBeenCalledTimes(1));

  fireEvent.change(screen.getByRole('textbox', { name: /^feedback$/i }), {
    target: { value: 'Looks good' },
  });
  fireEvent.click(screen.getByRole('button', { name: '승인' }));

  await waitFor(() => expect(submitFeedback).toHaveBeenCalledTimes(2));

  const firstKey = submitFeedback.mock.calls[0][0].idempotency_key;
  const secondKey = submitFeedback.mock.calls[1][0].idempotency_key;
  expect(firstKey).toBe('human-feedback:hfr_123:approved');
  expect(secondKey).toBe(firstKey);
});

test('confirms approve with feedback when the next node is Output', async () => {
  mockRunDetail({
    pending_human_feedback_request: makePendingHitlRequest({
      prompt_json: {
        message: 'HITL이 실행되었습니다. 계속 진행하시겠습니까?',
        next_node_id: 'output',
        remaining_retries: 3,
        preview_payload: { raw: 'content output v1' },
      },
    }),
  });
  const submitFeedback = mockHumanFeedbackSubmit();

  renderAtPath('/run');

  const feedbackBox = screen.getByRole('textbox', { name: /^feedback$/i });
  fireEvent.change(feedbackBox, {
    target: { value: 'Final pass note' },
  });
  fireEvent.click(screen.getByRole('button', { name: '승인' }));

  expect(submitFeedback).not.toHaveBeenCalled();
  expect(screen.getByText('피드백이 작성되었지만 다음으로 예정된 작업이 없습니다. 그래도 승인하시겠습니까?')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'N' }));
  expect(submitFeedback).not.toHaveBeenCalled();
  expect(screen.getByRole('textbox', { name: /^feedback$/i })).toHaveValue('Final pass note');

  fireEvent.click(screen.getByRole('button', { name: '승인' }));
  fireEvent.click(screen.getByRole('button', { name: 'Y' }));

  await waitFor(() =>
    expect(submitFeedback).toHaveBeenCalledWith(
      expect.objectContaining({
        request_id: 'hfr_123',
        outcome: 'approved',
        feedback: 'Final pass note',
      }),
    ),
  );
});

test('keeps retry disabled when retry budget is exhausted', () => {
  mockRunDetail({
    pending_human_feedback_request: makePendingHitlRequest({
      prompt_json: {
        message: 'HITL이 실행되었습니다. 계속 진행하시겠습니까?',
        next_node_id: 'crew:visual',
        remaining_retries: 0,
        preview_payload: { raw: 'content output v1' },
      },
    }),
  });

  renderAtPath('/run');

  expect(screen.getByRole('button', { name: '재시도' })).toBeDisabled();
  expect(screen.getByText('최대 재시도 횟수를 초과했습니다.')).toBeInTheDocument();
});

test('keeps retry disabled when computed retry budget is exhausted', () => {
  mockRunDetail({
    pending_human_feedback_request: makePendingHitlRequest({
      attempt_number: 4,
      prompt_json: {
        message: 'HITL이 실행되었습니다. 계속 진행하시겠습니까?',
        next_node_id: 'crew:visual',
        attempt_number: 4,
        max_attempts: 3,
        preview_payload: { raw: 'content output v1' },
      },
    }),
  });

  renderAtPath('/run');

  expect(screen.getByRole('button', { name: '재시도' })).toBeDisabled();
  expect(screen.getByText('최대 재시도 횟수를 초과했습니다.')).toBeInTheDocument();
});

test('refetches run detail when a hitl_requested WebSocket event arrives', async () => {
  const refetch = mockRunDetail({
    pending_human_feedback_request: null,
  });

  renderAtPath('/run');

  expect(FakeWebSocket.instances).toHaveLength(1);
  expect(FakeWebSocket.instances[0].url).toContain('/api/flow-runs/run-123/stream');
  expect(FakeWebSocket.instances[0].url).not.toContain('access_token=');

  FakeWebSocket.instances[0].onopen?.();
  expect(FakeWebSocket.instances[0].sentMessages).toContain(
    JSON.stringify({ type: 'authenticate', access_token: 'smoke-token' }),
  );

  FakeWebSocket.instances[0].emitMessage({ type: 'hitl_requested', run_id: 'run-123' });

  await waitFor(() => expect(refetch).toHaveBeenCalledTimes(1));
});

test('keeps the run stream connected while a background run is executing', () => {
  mockRunDetail({
    status: 'executing',
    pending_human_feedback_request: null,
  });

  renderAtPath('/run');

  expect(FakeWebSocket.instances).toHaveLength(1);
  expect(FakeWebSocket.instances[0].url).toContain('/api/flow-runs/run-123/stream');
});

test('ignores legacy allowed decisions in pending HITL request metadata', async () => {
  runHookMocks.selectedRunId = 'run-123';
  runHookMocks.useFlowRunDetail.mockReturnValue({
    run: {
      id: 'run-123',
      status: 'waiting_for_human',
      input_json: { topic: 'AI orchestration' },
      output_json: null,
      latest_state_snapshot: null,
      pending_human_feedback_request: {
        id: 'request-1',
        run_id: 'run-123',
        node_id: 'hitl:review',
        status: 'pending',
        prompt_json: {
          prompt: 'Review output',
          allowed_decisions: ['approved', 'rejected'],
          preview_payload: { final_answer: 'Draft' },
        },
        response_json: {},
        created_at: '2026-04-29T00:00:00Z',
      },
    },
    isLoading: false,
    error: null,
  });

  renderAtPath('/run');

  expect(screen.getByRole('button', { name: '승인' })).toBeEnabled();
  expect(screen.getByRole('button', { name: '재시도' })).toBeEnabled();
  expect(screen.getByRole('button', { name: '거절' })).toBeEnabled();
  fireEvent.change(screen.getByRole('textbox', { name: /^feedback$/i }), {
    target: { value: 'Looks fine' },
  });
  fireEvent.click(screen.getByRole('button', { name: '거절' }));

  await waitFor(() =>
    expect(runHookMocks.submitFeedbackSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        request_id: 'request-1',
        outcome: 'rejected',
        feedback: 'Looks fine',
        idempotency_key: 'human-feedback:request-1:rejected',
      }),
    ),
  );
});

test('keeps Retry enabled on the final human review attempt before the retry click is used', () => {
  runHookMocks.selectedRunId = 'run-123';
  runHookMocks.useFlowRunDetail.mockReturnValue({
    run: {
      id: 'run-123',
      status: 'waiting_for_human',
      input_json: { topic: 'AI orchestration' },
      output_json: null,
      latest_state_snapshot: null,
      pending_human_feedback_request: {
        id: 'request-1',
        run_id: 'run-123',
        node_id: 'hitl:review',
        status: 'pending',
        attempt_number: 3,
        prompt_json: {
          prompt: 'Review output',
          allowed_decisions: ['approved', 'needs_revision', 'rejected'],
          attempt_number: 3,
          max_attempts: 3,
          preview_payload: { final_answer: 'Draft' },
        },
        response_json: {},
        created_at: '2026-04-29T00:00:00Z',
      },
    },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  });

  renderAtPath('/run');

  expect(screen.getByRole('button', { name: '승인' })).toBeEnabled();
  expect(screen.getByRole('button', { name: '재시도' })).toBeEnabled();
  expect(screen.queryByText('최대 재시도 횟수를 초과했습니다.')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '거절' })).toBeEnabled();
});

test('keeps Retry enabled when retry budget metadata is absent', () => {
  mockRunDetail({
    pending_human_feedback_request: makePendingHitlRequest({
      attempt_number: null,
      prompt_json: {
        message: 'HITL이 실행되었습니다. 계속 진행하시겠습니까?',
        next_node_id: 'crew:visual',
        preview_payload: { raw: 'content output v1' },
      },
    }),
  });

  renderAtPath('/run');

  expect(screen.getByRole('button', { name: '재시도' })).toBeEnabled();
  expect(screen.queryByText('최대 재시도 횟수를 초과했습니다.')).not.toBeInTheDocument();
});

test('disables keyword input and sends empty inputs when the selected flow has no input node', async () => {
  runHookMocks.usePublishedFlowOptions.mockReturnValue({
    flows: [
      {
        assetId: 'flow-2',
        versionId: 'flow-version-2',
        name: 'No Input Flow',
        versionNo: 1,
        hasInputNode: false,
      },
    ],
    isLoading: false,
    error: null,
  });

  renderAtPath('/run');

  expect(screen.getByRole('textbox', { name: /키워드/i })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: /launch run/i }));

  await waitFor(() =>
    expect(runHookMocks.createRunSpy).toHaveBeenCalledWith({
      flow_version_id: 'flow-version-2',
      inputs: {},
      capture_agent_execution_logs: true,
    }),
  );
});

test('resets stale selected workflow when published flow options change', async () => {
  let flows = [
    {
      assetId: 'flow-1',
      versionId: 'flow-version-1',
      name: 'Launch Flow',
      versionNo: 3,
      hasInputNode: true,
    },
    {
      assetId: 'flow-2',
      versionId: 'flow-version-2',
      name: 'Retired Flow',
      versionNo: 1,
      hasInputNode: false,
    },
  ];
  runHookMocks.usePublishedFlowOptions.mockImplementation(() => ({
    flows,
    isLoading: false,
    error: null,
  }));

  const router = createMemoryRouter(appRoutes, { initialEntries: ['/run'] });
  const rendered = render(<RouterProvider router={router} />);

  fireEvent.change(screen.getByRole('combobox', { name: /workflow/i }), {
    target: { value: 'flow-version-2' },
  });
  expect(screen.getByRole('combobox', { name: /workflow/i })).toHaveDisplayValue('Retired Flow v1');

  flows = [
    {
      assetId: 'flow-3',
      versionId: 'flow-version-3',
      name: 'Replacement Flow',
      versionNo: 4,
      hasInputNode: true,
    },
  ];
  fireEvent.click(screen.getByRole('checkbox', { name: /에이전트 실행 로그 캡처/i }));
  rendered.rerender(<RouterProvider router={router} />);

  await waitFor(() =>
    expect(screen.getByRole('combobox', { name: /workflow/i })).toHaveDisplayValue('Replacement Flow v4'),
  );
  expect(screen.getByRole('textbox', { name: /키워드/i })).toBeEnabled();

  fireEvent.change(screen.getByRole('textbox', { name: /키워드/i }), {
    target: { value: 'replacement keyword' },
  });
  fireEvent.click(screen.getByRole('button', { name: /launch run/i }));

  await waitFor(() =>
    expect(runHookMocks.createRunSpy).toHaveBeenCalledWith({
      flow_version_id: 'flow-version-3',
      inputs: { topic: 'replacement keyword' },
      capture_agent_execution_logs: false,
    }),
  );
});

test('renders the streaming timeline for selected run events', () => {
  runHookMocks.selectedRunId = 'run-123';
  runHookMocks.useFlowRunDetail.mockReturnValue({
    run: {
      id: 'run-123',
      status: 'running',
      input_json: {},
      output_json: null,
      latest_state_snapshot: null,
    },
    isLoading: false,
    error: null,
  });
  runHookMocks.useFlowRunEvents.mockReturnValue({
    events: [
      {
        id: 'event-1',
        event_type: 'node_started',
        created_at: '2026-04-25T00:00:00Z',
        node_id: 'research',
        event_payload_json: { attempt: 1 },
      },
    ],
    isLoading: false,
    error: null,
  });

  renderAtPath('/run/streaming');

  expect(screen.getByRole('heading', { name: /^streaming$/i })).toBeInTheDocument();
  expect(screen.getByText(/^timeline$/i)).toBeInTheDocument();
  expect(screen.getByText(/node_started/i)).toBeInTheDocument();
  expect(screen.getByText(/research/i)).toBeInTheDocument();
  expect(screen.queryByText(/attempt/i)).not.toBeInTheDocument();
  const detailsButton = screen.getByRole('button', { name: /details for node_started event research event-1/i });
  expect(detailsButton).toHaveAttribute('aria-expanded', 'false');
  fireEvent.click(detailsButton);
  expect(detailsButton).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getByText(/attempt/i)).toBeInTheDocument();
  expect(screen.queryByText(/no events recorded yet/i)).not.toBeInTheDocument();
});

test('renders Nano Banana image generation progress on the Streaming page', () => {
  runHookMocks.selectedRunId = 'run-123';
  runHookMocks.useFlowRunDetail.mockReturnValue({
    run: {
      id: 'run-123',
      status: 'running',
      input_json: {},
      output_json: null,
      latest_state_snapshot: null,
    },
    isLoading: false,
    error: null,
  });
  runHookMocks.useFlowRunEvents.mockReturnValue({
    events: [
      {
        id: 'nano-start-1',
        event_type: 'image_generation_started',
        created_at: '2026-05-04T12:00:00Z',
        node_id: 'crew:visual',
        event_payload_json: {
          tool: 'nano_banana',
          prompt_preview: 'A carousel cover',
        },
      },
      {
        id: 'nano-failed-1',
        event_type: 'image_generation_failed',
        created_at: '2026-05-04T12:00:30Z',
        node_id: 'crew:visual',
        event_payload_json: {
          image_generation: true,
          error_message: 'Provider timeout',
          retryable: true,
        },
      },
    ],
    isLoading: false,
    error: null,
  });

  renderAtPath('/run/streaming');

  expect(screen.getByRole('heading', { name: /image generation progress/i })).toBeInTheDocument();
  expect(screen.getByText(/0 \/ 3 images complete/i)).toBeInTheDocument();
  expect(screen.getByText(/provider timeout/i)).toBeInTheDocument();
  expect(screen.getByText(/retryable/i)).toBeInTheDocument();
});

test('Streaming page shows timeline summaries with uniquely expandable raw details', () => {
  runHookMocks.selectedRunId = 'run-123';
  runHookMocks.useFlowRunDetail.mockReturnValue({
    run: { id: 'run-123', status: 'completed', input_json: {}, output_json: {}, latest_state_snapshot: null },
    isLoading: false,
    error: null,
  });
  runHookMocks.useFlowRunEvents.mockReturnValue({
    events: [
      {
        id: 'evt-1',
        event_type: 'run_started',
        node_id: null,
        event_payload_json: { flow_version_id: 'flow-v1' },
        created_at: '2026-04-29T00:00:00Z',
      },
      {
        id: 'evt-2',
        event_type: 'agent_finish',
        node_id: 'crew:writer',
        event_payload_json: { output: 'Done' },
        created_at: '2026-04-29T00:00:01Z',
      },
    ],
    isLoading: false,
    error: null,
  });

  renderAtPath('/run/streaming');

  expect(screen.getByText(/run started/i)).toBeInTheDocument();
  expect(screen.queryByText(/flow_version_id/i)).not.toBeInTheDocument();
  const runStartedDetails = screen.getByRole('button', { name: /details for run started event run evt-1/i });
  const agentFinishDetails = screen.getByRole('button', { name: /details for agent finish event crew:writer evt-2/i });
  expect(runStartedDetails).toHaveAttribute('aria-controls');
  expect(agentFinishDetails).toHaveAttribute('aria-controls');
  expect(runStartedDetails).not.toHaveAttribute('aria-controls', agentFinishDetails.getAttribute('aria-controls') ?? '');
  fireEvent.click(runStartedDetails);
  expect(screen.getByText(/flow_version_id/i)).toBeInTheDocument();
  expect(screen.queryByText(/"output": "Done"/i)).not.toBeInTheDocument();
});

test('renders captured agent execution log events with readable labels', () => {
  runHookMocks.selectedRunId = 'run-123';
  runHookMocks.useFlowRunDetail.mockReturnValue({
    run: {
      id: 'run-123',
      status: 'completed',
      input_json: {},
      output_json: null,
      latest_state_snapshot: null,
    },
    isLoading: false,
    error: null,
  });
  runHookMocks.useFlowRunEvents.mockReturnValue({
    events: [
      {
        id: 'event-agent-step',
        event_type: 'agent_step',
        created_at: '2026-04-25T00:00:00Z',
        node_id: 'crew:research',
        event_payload_json: {
          crew_node_id: 'crew:research',
          kind: 'agent_step',
          thought: 'Need search',
          tool: 'search_docs',
          tool_input: '{"query":"CrewAI"}',
        },
      },
      {
        id: 'event-agent-finish',
        event_type: 'agent_finish',
        created_at: '2026-04-25T00:00:01Z',
        node_id: 'crew:research',
        event_payload_json: {
          crew_node_id: 'crew:research',
          kind: 'agent_finish',
          output: 'researched CrewAI',
        },
      },
    ],
    isLoading: false,
    error: null,
  });

  renderAtPath('/run/streaming');

  expect(screen.getByText(/agent step/i)).toBeInTheDocument();
  expect(screen.getByText(/agent finish/i)).toBeInTheDocument();
  expect(screen.getByText(/^need search$/i)).toHaveClass('break-words', 'whitespace-pre-wrap');
  expect(screen.getByText(/^tool: search_docs$/i)).toBeInTheDocument();
  expect(screen.getByText(/^input: {"query":"crewai"}$/i)).toHaveClass('break-words', 'whitespace-pre-wrap');
  expect(screen.getByText(/^researched crewai$/i)).toHaveClass('break-words', 'whitespace-pre-wrap');
});

test('renders the streaming empty state when no events exist', () => {
  runHookMocks.selectedRunId = 'run-123';

  renderAtPath('/run/streaming');

  expect(screen.getByRole('heading', { name: /^streaming$/i })).toBeInTheDocument();
  expect(screen.getByText(/^timeline$/i)).toBeInTheDocument();
  expect(screen.getByText(/no events recorded yet/i)).toBeInTheDocument();
});

test('lets users reach run subpages through the in-app run navigation', () => {
  const router = renderAtPath('/run');

  expect(screen.getByRole('link', { name: /^run$/i })).toHaveAttribute('aria-current', 'page');
  expect(screen.getByRole('link', { name: /^streaming$/i })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /^i\/o$/i })).toBeInTheDocument();

  fireEvent.click(screen.getByRole('link', { name: /^streaming$/i }));
  expect(router.state.location.pathname).toBe('/run/streaming');
  expect(screen.getByRole('heading', { name: /^streaming$/i })).toBeInTheDocument();

  fireEvent.click(screen.getByRole('link', { name: /^i\/o$/i }));
  expect(router.state.location.pathname).toBe('/run/io');
  expect(screen.getByRole('heading', { name: /^i\/o$/i })).toBeInTheDocument();
});
