import type { components } from '../types/api.generated';
import { apiBaseUrl, client } from './client';

export type FlowRunCreateRequest = components['schemas']['FlowRunCreateRequest'];
export type FlowRunResponse = components['schemas']['FlowRunResponse'];
export type FlowRunDetailResponse = components['schemas']['FlowRunDetailResponse'];
export type HumanFeedbackSubmitRequest = components['schemas']['HumanFeedbackSubmitRequest'];

export function createFlowRun(body: FlowRunCreateRequest) {
  return client.POST('/api/flow-runs', { body });
}

export function getFlowRun(runId: string) {
  return client.GET('/api/flow-runs/{run_id}', {
    params: {
      path: {
        run_id: runId,
      },
    },
  });
}

export function listFlowRunEvents(runId: string) {
  return client.GET('/api/flow-runs/{run_id}/events', {
    params: {
      path: {
        run_id: runId,
      },
    },
  });
}

export function flowRunStreamUrl(runId: string) {
  const base =
    apiBaseUrl.length > 0 ? new URL(apiBaseUrl, window.location.origin) : new URL(window.location.origin);
  base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:';
  base.pathname = `/api/flow-runs/${encodeURIComponent(runId)}/stream`;
  base.search = '';

  return base.toString();
}

export function submitHumanFeedback(runId: string, body: HumanFeedbackSubmitRequest) {
  return client.POST('/api/flow-runs/{run_id}/human-feedback', {
    params: {
      path: {
        run_id: runId,
      },
    },
    body,
  });
}
