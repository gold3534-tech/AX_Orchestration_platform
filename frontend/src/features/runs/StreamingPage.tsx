import { useState } from 'react';
import { PageFrame } from '../../components/layout/PageFrame';
import { PageHeader } from '../../components/platform/PageHeader';
import { readSelectedRunId, useFlowRunDetail, useFlowRunEvents } from './hooks';
import { RunSidebar } from '../../components/layout/Sidebar';
import { RawJsonInspect } from './OutputPreview';
import { ImageGenerationProgressPanel } from './ImageGenerationProgressPanel';
import { buildImageProgressGroups } from './imageProgressModel';

function eventValue(event: Record<string, unknown>, key: string) {
  const value = event[key];
  return typeof value === 'string' ? value : null;
}

function shouldPollEvents(status: string | undefined) {
  return status === undefined || status === 'running' || status === 'executing' || status === 'waiting_for_human';
}

function eventTitle(eventType: string) {
  const titles: Record<string, string> = {
    agent_step: 'Agent step',
    agent_tool_result: 'Tool result',
    agent_finish: 'Agent finish',
    task_completed: 'Task completed',
    telemetry_error: 'Telemetry error',
    run_started: 'Run started',
    crew_started: 'Crew started',
    crew_completed: 'Crew completed',
    hitl_requested: 'HITL requested',
    run_failed: 'Run failed',
    run_completed: 'Run completed',
  };
  return titles[eventType] ?? eventType;
}

function payloadRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function payloadText(payload: Record<string, unknown>, key: string) {
  const value = payload[key];
  return typeof value === 'string' && value.trim() ? value : null;
}

function safeId(value: string) {
  return value.replace(/[^a-zA-Z0-9_-]+/g, '-');
}

function EventDetails({ payload, detailsId, label }: { payload: unknown; detailsId: string; label: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-3">
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        aria-controls={detailsId}
        onClick={() => setOpen((value) => !value)}
        className="rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-3 py-2 text-xs font-bold text-[#22170f]"
      >
        Details
      </button>
      {open ? (
        <div id={detailsId} className="mt-3">
          <RawJsonInspect value={payload} />
        </div>
      ) : null}
    </div>
  );
}

export function StreamingPage() {
  const runId = readSelectedRunId();
  const { run, isLoading: isRunLoading, error: runError } = useFlowRunDetail(runId);
  const { events, isLoading: areEventsLoading, error: eventsError } = useFlowRunEvents(runId, {
    pollingEnabled: shouldPollEvents(run?.status),
  });
  const imageProgressGroups = buildImageProgressGroups(events);

  return (
    <PageFrame sidebar={<RunSidebar />}>
      <PageHeader title="Streaming" description="Follow the selected workflow run event timeline." />

      {!runId ? <p className="text-sm text-stone-500">Launch or select a run from the Run page.</p> : null}
      {runId && isRunLoading ? <p className="mb-4 text-sm text-stone-500">Loading selected run status.</p> : null}
      {runError ? <p className="mb-4 text-sm text-red-300">{runError}</p> : null}
      {areEventsLoading ? <p className="mb-4 text-sm text-stone-500">Loading run events.</p> : null}
      {eventsError ? <p className="mb-4 text-sm text-red-300">{eventsError}</p> : null}

      <div className="mb-6">
        <ImageGenerationProgressPanel groups={imageProgressGroups} />
      </div>

      <section className="pixel-panel bg-[#fff6df] p-5">
        <p className="text-xs font-semibold uppercase text-[#2f9b96]">Timeline</p>
        <div className="mt-4 space-y-3">
          {!areEventsLoading && events.length === 0 ? <p className="text-sm text-stone-500">No events recorded yet.</p> : null}
          {events.map((event, index) => {
            const eventId = eventValue(event, 'id') ?? `${index}`;
            const eventType = eventValue(event, 'event_type') ?? 'event';
            const createdAt = eventValue(event, 'created_at') ?? '';
            const nodeId = eventValue(event, 'node_id') ?? 'run';
            const payload = event.event_payload_json ?? {};
            const recordPayload = payloadRecord(payload);
            const thought = payloadText(recordPayload, 'thought');
            const tool = payloadText(recordPayload, 'tool');
            const toolInput = payloadText(recordPayload, 'tool_input');
            const result = payloadText(recordPayload, 'result');
            const output = payloadText(recordPayload, 'output');
            const title = eventTitle(eventType);
            const detailsId = `run-event-details-${safeId(eventId)}`;
            const detailsLabel = `Details for ${title} event ${nodeId} ${eventId}`;

            return (
              <article key={eventId} className="rounded-md border-2 border-[#7a5739] bg-[#fffaf0] p-4 shadow-[3px_3px_0_rgba(122,87,57,0.35)]">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-sm font-semibold text-stone-900">{title}</p>
                  <p className="text-xs text-stone-500">{createdAt}</p>
                </div>
                <p className="mt-1 text-xs text-stone-500">{nodeId}</p>
                {thought ? <p className="mt-3 whitespace-pre-wrap break-words text-sm text-stone-700">{thought}</p> : null}
                {tool ? <p className="mt-2 text-xs font-semibold text-[#2f9b96]">Tool: {tool}</p> : null}
                {toolInput ? (
                  <p className="mt-1 whitespace-pre-wrap break-words text-xs text-stone-500">Input: {toolInput}</p>
                ) : null}
                {result ? <p className="mt-2 whitespace-pre-wrap break-words text-xs text-emerald-700">Result: {result}</p> : null}
                {output ? <p className="mt-2 whitespace-pre-wrap break-words text-sm text-emerald-800">{output}</p> : null}
                <EventDetails payload={payload} detailsId={detailsId} label={detailsLabel} />
              </article>
            );
          })}
        </div>
      </section>
    </PageFrame>
  );
}
