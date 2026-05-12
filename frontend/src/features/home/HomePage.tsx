import { useMemo, useState } from 'react';
import {
  readSelectedRunId,
  type PublishedFlowOption,
  useCreateFlowRunMutation,
  useFlowRunDetail,
  useFlowRunEvents,
  useSubmitHumanFeedbackMutation,
  writeSelectedRunId,
} from '../runs/hooks';
import { buildStreamingScene } from '../streaming/streamingEventModel';
import { HomeFlowStartPopup } from './HomeFlowStartPopup';
import { HomePixiStage } from './HomePixiStage';
import FlowRunnerPanel from './FlowRunnerPanel';

function shouldPollEvents(status: string | undefined) {
  return status === undefined || status === 'running' || status === 'executing' || status === 'waiting_for_human';
}

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
  if (!isRecord(state) || !isRecord(state.node_outputs)) return run.output_json ?? {};
  const outputs = Object.values(state.node_outputs);
  for (let index = outputs.length - 1; index >= 0; index -= 1) {
    if (isRecord(outputs[index])) return outputs[index];
  }
  return run.output_json ?? {};
}

export function HomePage() {
  const [runId, setRunId] = useState(() => readSelectedRunId());
  const [closedHitlRequestId, setClosedHitlRequestId] = useState<string | null>(null);
  const [hiddenResultReportId, setHiddenResultReportId] = useState<string | null>(null);
  const [flowStartTarget, setFlowStartTarget] = useState<PublishedFlowOption | null>(null);
  const { run, isLoading: isRunLoading, error: runError } = useFlowRunDetail(runId);
  const { events, isLoading: areEventsLoading, error: eventsError } = useFlowRunEvents(runId, {
    pollingEnabled: shouldPollEvents(run?.status),
  });
  const feedbackMutation = useSubmitHumanFeedbackMutation(runId);
  const createRun = useCreateFlowRunMutation();
  const humanFeedbackRequest = run?.pending_human_feedback_request ?? null;
  const visibleHumanFeedbackRequest =
    humanFeedbackRequest && humanFeedbackRequest.id !== closedHitlRequestId ? humanFeedbackRequest : null;
  const isWaitingForHuman = run?.status === 'waiting_for_human' || Boolean(humanFeedbackRequest);
  const currentEvent = events.at(-1);
  const currentEventType = typeof currentEvent?.event_type === 'string' ? currentEvent.event_type : '??';
  const currentEventTime = typeof currentEvent?.created_at === 'string' ? currentEvent.created_at : '';
  const hasParseWarning = events.some((event) => {
    const payload = isRecord(event.event_payload_json) ? event.event_payload_json : {};
    const message = Object.values(payload)
      .filter((value): value is string => typeof value === 'string')
      .join(' ')
      .toLowerCase();
    return message.includes('failed to parse llm response') || message.includes('parse llm');
  });
  const resultReport = useMemo(
    () =>
      run?.status === 'completed' || run?.status === 'failed'
        ? { id: `${runId ?? 'run'}:${run.status}:${currentEventTime}`, output: validationFallbackOutput(run), hasWarning: hasParseWarning }
        : null,
    [currentEventTime, hasParseWarning, run, runId],
  );
  const visibleResultReport =
    resultReport && resultReport.id !== hiddenResultReportId && !flowStartTarget ? resultReport : null;

  const scene = useMemo(() => {
    const knownAgentNames: string[] = [];
    const runtimeAgentMap: Record<string, Record<string, unknown>> = {};
    const runtimeAgentByRole: Record<string, { id: string; agent: Record<string, unknown> }> = {};
    const snapshot = run?.latest_state_snapshot?.state_json;
    const entities = isRecord(snapshot)
      ? isRecord(snapshot.entities)
        ? snapshot.entities
        : isRecord(snapshot.published_snapshot_entities)
          ? snapshot.published_snapshot_entities
          : null
      : null;
    const crews = isRecord(entities?.crews) ? entities.crews : null;

    if (crews) {
      for (const crew of Object.values(crews)) {
        if (!isRecord(crew) || !isRecord(crew.runtime_snapshot_json)) continue;
        const runtimeAgents = isRecord(crew.runtime_snapshot_json.runtime_agents)
          ? crew.runtime_snapshot_json.runtime_agents
          : {};
        for (const [agentId, agent] of Object.entries(runtimeAgents)) {
          if (!isRecord(agent)) continue;
          const name = typeof agent.agent_name === 'string' ? agent.agent_name : typeof agent.name === 'string' ? agent.name : '';
          const role = typeof agent.role === 'string' ? agent.role : typeof agent.agent_role === 'string' ? agent.agent_role : '';
          if (name.trim()) knownAgentNames.push(name.replace(/[-_:]+/g, ' ').trim());
          runtimeAgentMap[agentId] = agent;
          [name, role].forEach((key) => {
            if (!key.trim()) return;
            runtimeAgentByRole[key.replace(/[-_:]+/g, ' ').trim().toLowerCase()] = { id: agentId, agent };
          });
        }
      }
    }

    const enrichedEvents = events.map((event) => {
      const payload = isRecord(event.event_payload_json) ? { ...event.event_payload_json } : {};
      const agentId =
        typeof payload.agent_id === 'string'
          ? payload.agent_id
          : typeof payload.agent_version_id === 'string'
            ? payload.agent_version_id
            : null;
      const meta = agentId ? runtimeAgentMap[agentId] : undefined;

      if (meta && !payload.agent_name) {
        payload.agent_name = meta.agent_name ?? meta.name;
        payload.agent_role = payload.agent_role ?? meta.role ?? meta.agent_role;
        payload.goal = payload.goal ?? meta.goal;
      }

      const fromRole = typeof payload.from_agent_role === 'string' ? payload.from_agent_role : null;
      const toRole = typeof payload.to_agent_role === 'string' ? payload.to_agent_role : null;
      const fromMeta = fromRole ? runtimeAgentByRole[fromRole.replace(/[-_:]+/g, ' ').trim().toLowerCase()] : undefined;
      const toMeta = toRole ? runtimeAgentByRole[toRole.replace(/[-_:]+/g, ' ').trim().toLowerCase()] : undefined;
      if (fromMeta) {
        payload.from_agent_id = payload.from_agent_id ?? fromMeta.id;
        payload.from_agent_name = payload.from_agent_name ?? fromMeta.agent.agent_name ?? fromMeta.agent.name;
      }
      if (toMeta) {
        payload.to_agent_id = payload.to_agent_id ?? toMeta.id;
        payload.to_agent_name = payload.to_agent_name ?? toMeta.agent.agent_name ?? toMeta.agent.name;
      }

      return { ...event, event_payload_json: payload };
    });

    return buildStreamingScene(enrichedEvents, isWaitingForHuman, knownAgentNames);
  }, [events, isWaitingForHuman, run]);

  async function submitHitlDecision(outcome: 'approved' | 'rejected', feedback: string) {
    if (!humanFeedbackRequest) return;
    const requestId = humanFeedbackRequest.id;
    setClosedHitlRequestId(requestId);
    try {
      await feedbackMutation.mutateAsync({
        request_id: requestId,
        outcome,
        feedback,
      });
    } catch (error) {
      setClosedHitlRequestId(null);
      throw error;
    }
  }

  async function startFlowFromPopup(inputs: Record<string, unknown>) {
    if (!flowStartTarget) return;
    const runResponse = await createRun.mutateAsync({
      flow_version_id: flowStartTarget.versionId,
      inputs,
      capture_agent_execution_logs: true,
    });
    writeSelectedRunId(runResponse.id);
    setRunId(runResponse.id);
    setFlowStartTarget(null);
  }

  function openFlowStartPopup(flow: PublishedFlowOption) {
    if (resultReport) setHiddenResultReportId(resultReport.id);
    setFlowStartTarget(flow);
  }

  return (
    <main className="w-full min-w-0 flex-1 overflow-auto bg-transparent">
      <h1 className="sr-only">Home</h1>
      <div className="mx-auto flex min-h-[calc(100vh-5rem)] w-full max-w-[1800px] gap-4 px-5 py-5 2xl:px-6">
        <div className="flex min-h-[calc(100vh-7.5rem)] flex-1 flex-col">
          <div className="relative flex-1">
            <HomePixiStage
              agents={scene.agents}
              edgeToEdge
              fullHeight
              isAnimationPaused={Boolean(visibleHumanFeedbackRequest)}
              resultReport={visibleResultReport}
              hitlRequest={visibleHumanFeedbackRequest}
              isHitlBusy={feedbackMutation.isPending}
              hitlSubmitError={feedbackMutation.error instanceof Error ? feedbackMutation.error.message : null}
              onSubmitHitl={submitHitlDecision}
            />
            {flowStartTarget ? (
              <HomeFlowStartPopup
                flow={flowStartTarget}
                isBusy={createRun.isPending}
                error={createRun.error instanceof Error ? createRun.error.message : null}
                onCancel={() => setFlowStartTarget(null)}
                onStart={startFlowFromPopup}
              />
            ) : null}
          </div>

          <div className="mt-4 rounded-md border-2 border-[#7a5739] bg-[#fff6df]/90 px-4 py-3 shadow-[4px_4px_0_rgba(80,48,24,0.16)]">
            {!runId ? <p className="text-sm font-semibold text-stone-700">Launch or select a run from the Run page.</p> : null}
            {runId && isRunLoading ? <p className="text-sm font-semibold text-stone-700">Loading selected run status.</p> : null}
            {runError ? <p className="text-sm font-bold text-red-700">{runError}</p> : null}
            {areEventsLoading ? <p className="text-sm font-semibold text-stone-700">Loading run events.</p> : null}
            {eventsError ? <p className="text-sm font-bold text-red-700">{eventsError}</p> : null}
          </div>
        </div>

        <div className="flex w-80 flex-col gap-4">
          <FlowRunnerPanel onStartRequested={openFlowStartPopup} />
          <div className="rounded-md border-2 border-[#7a5739] bg-white/95 p-3 text-sm shadow-[4px_4px_0_rgba(80,48,24,0.18)]">
            <p className="text-xs font-black uppercase tracking-[0.16em] text-[#2f9b96]">Current run event</p>
            {currentEvent ? (
              <div className="mt-2">
                <p className="text-sm font-black text-stone-950">{currentEventType}</p>
                <p className="text-xs font-semibold text-stone-600">{currentEventTime}</p>
              </div>
            ) : (
              <p className="mt-2 text-sm font-semibold text-stone-600">No events yet</p>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
