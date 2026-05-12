import { useCallback, useEffect, useRef, useState } from 'react';
import { PageFrame } from '../../components/layout/PageFrame';
import { PageHeader } from '../../components/platform/PageHeader';
import {
  readSelectedRunId,
  useCreateFlowRunMutation,
  useFlowRunDetail,
  useFlowRunEvents,
  usePublishedFlowOptions,
  useSubmitHumanFeedbackMutation,
  writeSelectedRunId,
} from './hooks';
import { RunSidebar } from '../../components/layout/Sidebar';
import { useFlowRunStream } from './useFlowRunStream';
import { OutputPreview } from './OutputPreview';
import { HumanFeedbackDialog } from './HumanFeedbackDialog';
import { ImageGenerationProgressPanel } from './ImageGenerationProgressPanel';
import { buildImageProgressGroups } from './imageProgressModel';

type HumanFeedbackOutcome = 'approved' | 'needs_revision' | 'rejected';

type HumanFeedbackIdempotencyKeys = {
  requestId: string | null;
  keys: Partial<Record<HumanFeedbackOutcome, string>>;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function isEmptyRecord(value: unknown) {
  return isRecord(value) && Object.keys(value).length === 0;
}

function validationFallbackOutput(
  run: { output_json?: unknown; artifacts?: unknown[]; latest_state_snapshot?: { state_json?: unknown } | null } | null,
) {
  if (!run) return {};
  if (Array.isArray(run.artifacts) && run.artifacts.length > 0) {
    return {
      output_json: run.output_json ?? {},
      artifacts: run.artifacts,
    };
  }
  if (run.output_json !== null && run.output_json !== undefined && !isEmptyRecord(run.output_json)) {
    return run.output_json;
  }

  const state = run.latest_state_snapshot?.state_json;
  if (!isRecord(state)) return run.output_json ?? {};
  const nodeOutputs = state.node_outputs;
  if (!isRecord(nodeOutputs)) return run.output_json ?? {};

  const outputs = Object.values(nodeOutputs);
  for (let index = outputs.length - 1; index >= 0; index -= 1) {
    const output = outputs[index];
    if (isRecord(output)) {
      return output;
    }
  }

  return run.output_json ?? {};
}

export function RunPage() {
  const { flows, isLoading, error } = usePublishedFlowOptions();
  const createRun = useCreateFlowRunMutation();
  const [selectedFlowAssetVersionId, setSelectedFlowAssetVersionId] = useState('');
  const [selectedRunId, setSelectedRunId] = useState<string | null>(() => readSelectedRunId());
  const [keyword, setKeyword] = useState('');
  const [captureAgentExecutionLogs, setCaptureAgentExecutionLogs] = useState(true);
  const [formError, setFormError] = useState<string | null>(null);
  const { run, isLoading: isRunLoading, error: runError, refetch: refetchRunDetail } = useFlowRunDetail(selectedRunId);
  const streamEnabled = run?.status === 'running' || run?.status === 'executing' || run?.status === 'waiting_for_human';
  const { events } = useFlowRunEvents(selectedRunId, {
    pollingEnabled: streamEnabled,
  });
  const submitFeedback = useSubmitHumanFeedbackMutation(selectedRunId);
  const feedbackIdempotencyKeysRef = useRef<HumanFeedbackIdempotencyKeys>({ requestId: null, keys: {} });
  const handleHitlRequested = useCallback(() => {
    void refetchRunDetail();
  }, [refetchRunDetail]);

  useFlowRunStream({
    runId: selectedRunId ?? undefined,
    enabled: Boolean(selectedRunId) && streamEnabled,
    onHitlRequested: handleHitlRequested,
  });

  useEffect(() => {
    if (!selectedFlowAssetVersionId || !flows.some((flow) => flow.versionId === selectedFlowAssetVersionId)) {
      setSelectedFlowAssetVersionId(flows[0]?.versionId ?? '');
    }
  }, [flows, selectedFlowAssetVersionId]);

  const pendingRequest = run?.pending_human_feedback_request ?? null;
  const isBusy = createRun.isPending || submitFeedback.isPending;
  const selectedFlow = flows.find((flow) => flow.versionId === selectedFlowAssetVersionId) ?? null;
  const keywordEnabled = Boolean(selectedFlow?.hasInputNode);
  const imageProgressGroups = buildImageProgressGroups(events);

  useEffect(() => {
  }, [selectedRunId]);

  useEffect(() => {
    feedbackIdempotencyKeysRef.current = { requestId: pendingRequest?.id ?? null, keys: {} };
  }, [pendingRequest?.id]);

  async function handleLaunch() {
    setFormError(null);
    if (!selectedFlowAssetVersionId) {
      setFormError('Select a published workflow before launching.');
      return;
    }
    if (!selectedFlow) {
      setFormError('Select a published workflow before launching.');
      return;
    }
    const launchInputs = keywordEnabled ? { topic: keyword } : {};
    const runResponse = await createRun.mutateAsync({
      flow_version_id: selectedFlow.versionId,
      inputs: launchInputs,
      capture_agent_execution_logs: captureAgentExecutionLogs,
    });
    setSelectedRunId(runResponse.id);
    writeSelectedRunId(runResponse.id);
  }

  async function submitHumanDecision(outcome: HumanFeedbackOutcome, feedbackValue: string) {
    if (!pendingRequest) {
      return;
    }
    const cachedKeys = feedbackIdempotencyKeysRef.current;
    if (cachedKeys.requestId !== pendingRequest.id) {
      cachedKeys.requestId = pendingRequest.id;
      cachedKeys.keys = {};
    }
    cachedKeys.keys[outcome] ??= `human-feedback:${pendingRequest.id}:${outcome}`;
    await submitFeedback.mutateAsync({
      request_id: pendingRequest.id,
      outcome,
      feedback: feedbackValue,
      idempotency_key: cachedKeys.keys[outcome],
    });
  }

  return (
    <PageFrame sidebar={<RunSidebar />}>
      <PageHeader title="Run" description="Launch live workflow runs and review their output." />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(360px,0.8fr)]">
        <section className="rounded-md border-2 border-[#7a5739] bg-[#fff6df] p-5 shadow-[6px_6px_0_rgba(80,48,24,0.18)]">
          <div className="mb-4">
            <p className="text-xs font-black uppercase tracking-[0.18em] text-[#2f9b96]">Launch</p>
            <h2 className="mt-1 text-xl font-black text-stone-950">Published workflow</h2>
          </div>

          {error ? <p className="mb-3 text-sm font-bold text-red-700">{error}</p> : null}
          {formError ? <p className="mb-3 text-sm font-bold text-red-700">{formError}</p> : null}
          {createRun.error instanceof Error ? <p className="mb-3 text-sm font-bold text-red-700">{createRun.error.message}</p> : null}

          <label className="block text-sm font-black text-stone-800">
            Workflow
            <select
              value={selectedFlowAssetVersionId}
              onChange={(event) => setSelectedFlowAssetVersionId(event.target.value)}
              disabled={isLoading || flows.length === 0}
              className="mt-2 w-full rounded-md border-2 border-[#9a7a54] bg-[#fff6df] px-3 py-2 text-sm font-semibold text-stone-950 outline-none focus:border-[#2f9b96]"
            >
              {flows.map((flow) => (
                <option key={flow.versionId} value={flow.versionId}>
                  {flow.name} v{flow.versionNo}
                </option>
              ))}
            </select>
          </label>

          <label className="mt-4 block text-sm font-black text-stone-800">
            키워드
            <textarea
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              rows={5}
              disabled={!keywordEnabled}
              aria-describedby="run-keyword-help"
              className="mt-2 w-full rounded-md border-2 border-[#9a7a54] bg-[#fff6df] px-3 py-2 text-sm font-semibold text-stone-950 outline-none focus:border-[#2f9b96] disabled:cursor-not-allowed disabled:opacity-50"
            />
          </label>
          <p id="run-keyword-help" className="mt-2 text-xs font-semibold text-stone-600">
            {keywordEnabled
              ? '선택한 Flow의 Input Node가 이 값을 CrewAI {topic} 입력으로 전달합니다.'
              : '선택한 Flow에 Input Node가 없어 이번 실행에는 키워드 입력을 사용하지 않습니다.'}
          </p>

          <label className="mt-4 flex items-start gap-3 rounded-md border-2 border-[#d7b98b] bg-[#fff6df] px-3 py-3 text-sm font-semibold text-stone-700">
            <input
              type="checkbox"
              checked={captureAgentExecutionLogs}
              onChange={(event) => setCaptureAgentExecutionLogs(event.target.checked)}
              className="mt-1 h-4 w-4 rounded-sm border-[#7a5739] bg-[#fffaf0] text-[#2f9b96]"
            />
            <span>
              <span className="block font-semibold">에이전트 실행 로그 캡처</span>
              <span className="mt-1 block text-xs text-stone-600">
                이번 실행에서 AX가 안전한 내부 콜백으로 에이전트 단계와 태스크 완료 이벤트를 저장합니다.
              </span>
            </span>
          </label>

          <div className="mt-4 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={handleLaunch}
              disabled={isBusy || flows.length === 0}
              className="pixel-button bg-[#ef8b2c] px-4 py-2 text-sm font-black text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              Launch run
            </button>
          </div>

          {createRun.isPending ? (
            <div className="mt-4 rounded-md border-2 border-[#7a5739] bg-[#fffaf0] p-3">
              <div className="h-2 overflow-hidden rounded-sm border border-[#7a5739] bg-[#f8e8c8]">
                <div className="h-full w-1/2 animate-pulse bg-[#2f9b96]" />
              </div>
              <p className="mt-2 text-xs text-stone-700">실행 중입니다. 완료 후 Streaming 탭에서 캡처된 이벤트를 확인할 수 있습니다.</p>
            </div>
          ) : null}
        </section>

        <section className="rounded-md border-2 border-[#7a5739] bg-[#fff6df] p-5 shadow-[6px_6px_0_rgba(80,48,24,0.18)]">
          <p className="text-xs font-black uppercase tracking-[0.18em] text-[#2f9b96]">Current run</p>
          <h2 className="mt-1 text-xl font-black text-stone-950">
            {run ? run.status : selectedRunId && isRunLoading ? 'Loading run...' : runError ? 'Run unavailable' : 'No run selected'}
          </h2>
          {selectedRunId && isRunLoading ? <p className="mt-4 text-sm font-semibold text-stone-600">Loading selected run details.</p> : null}
          {runError ? <p className="mt-4 text-sm font-bold text-red-700">{runError}</p> : null}
          {selectedRunId && !isRunLoading && !runError && !run ? (
            <p className="mt-4 text-sm font-semibold text-stone-600">Selected run details are not available.</p>
          ) : null}
          {run ? (
            <div className="mt-4 space-y-4">
              <p className="text-sm font-semibold text-stone-600">Run ID: {run.id}</p>
              {run.status === 'failed' && run.error_message ? (
                <div className="rounded-md border-2 border-red-300 bg-red-50 p-3 text-sm font-semibold text-red-800">
                  {run.error_message}
                </div>
              ) : null}
              <div id="run-result-panel" role="tabpanel" aria-labelledby="run-result-tab">
                <OutputPreview value={validationFallbackOutput(run)} />
              </div>
            </div>
          ) : null}

        </section>
      </div>

      <div className="mt-6">
        <ImageGenerationProgressPanel groups={imageProgressGroups} />
      </div>

      <HumanFeedbackDialog
        pendingRequest={pendingRequest}
        isBusy={isBusy}
        submitError={submitFeedback.error instanceof Error ? submitFeedback.error.message : null}
        onSubmit={submitHumanDecision}
      />
    </PageFrame>
  );
}
