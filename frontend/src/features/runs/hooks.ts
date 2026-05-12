import { useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { listPublishedFlowsForRun } from '../../api/flowGraphs';
import {
  createFlowRun,
  flowRunStreamUrl,
  getFlowRun,
  listFlowRunEvents,
  submitHumanFeedback,
  type FlowRunCreateRequest,
  type HumanFeedbackSubmitRequest,
} from '../../api/runs';
import { getStoredAccessToken } from '../../hooks/useAuth';

export type PublishedFlowOption = {
  assetId: string;
  versionId: string;
  name: string;
  description?: string | null;
  versionNo: number;
  hasInputNode: boolean;
};

export const runQueryKeys = {
  publishedFlows: ['runs', 'published-flows'] as const,
  detail: (runId: string | null) => ['runs', 'detail', runId] as const,
  events: (runId: string | null) => ['runs', 'events', runId] as const,
};

function formatErrorDetail(detail: unknown): string | null {
  if (typeof detail === 'string') {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => formatErrorDetail(item))
      .filter((item): item is string => Boolean(item))
      .join('; ');
  }
  if (detail && typeof detail === 'object') {
    try {
      return JSON.stringify(detail);
    } catch {
      return null;
    }
  }

  return null;
}

function errorMessage(error: unknown, fallback: string) {
  if (error && typeof error === 'object' && 'detail' in error) {
    return formatErrorDetail((error as { detail?: unknown }).detail) ?? fallback;
  }

  return fallback;
}

function requireData<TData>(data: TData | undefined, fallback: string) {
  if (data === undefined) {
    throw new Error(fallback);
  }

  return data;
}

export function usePublishedFlowOptions() {
  const query = useQuery({
    queryKey: runQueryKeys.publishedFlows,
    queryFn: async () => {
      const flows = await listPublishedFlowsForRun();

      return flows.map(
        (flow): PublishedFlowOption => ({
          assetId: flow.asset_id,
          versionId: flow.version_id,
          name: flow.name,
          description: flow.description,
          versionNo: flow.version_no,
          hasInputNode: flow.has_input_node,
        }),
      );
    },
  });

  return {
    flows: query.data ?? [],
    isLoading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
  };
}

export function useCreateFlowRunMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (body: FlowRunCreateRequest) => {
      const response = await createFlowRun(body);
      if (response.error) {
        throw new Error(errorMessage(response.error, 'Failed to start run'));
      }

      return requireData(response.data, 'Failed to start run');
    },
    onSuccess(run) {
      queryClient.invalidateQueries({ queryKey: runQueryKeys.detail(run.id) });
      queryClient.invalidateQueries({ queryKey: runQueryKeys.events(run.id) });
    },
  });
}

export function useFlowRunDetail(runId: string | null) {
  const query = useQuery({
    queryKey: runQueryKeys.detail(runId),
    enabled: Boolean(runId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'running' || status === 'executing' || status === 'waiting_for_human' ? 2500 : false;
    },
    queryFn: async () => {
      const response = await getFlowRun(runId as string);
      if (response.error) {
        throw new Error(errorMessage(response.error, 'Failed to load run'));
      }

      return requireData(response.data, 'Failed to load run');
    },
  });

  return {
    run: query.data ?? null,
    isLoading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
    refetch: query.refetch,
  };
}

export function useFlowRunEvents(runId: string | null, options: { pollingEnabled?: boolean } = {}) {
  const queryClient = useQueryClient();
  const pollingEnabled = options.pollingEnabled ?? true;
  const query = useQuery({
    queryKey: runQueryKeys.events(runId),
    enabled: Boolean(runId),
    refetchInterval: runId && pollingEnabled ? 1000 : false,
    refetchIntervalInBackground: true,
    queryFn: async () => {
      const response = await listFlowRunEvents(runId as string);
      if (response.error) {
        throw new Error(errorMessage(response.error, 'Failed to load run events'));
      }

      return response.data?.events ?? [];
    },
  });

  useEffect(() => {
    if (!runId || typeof WebSocket === 'undefined') return undefined;

    const socket = new WebSocket(flowRunStreamUrl(runId));
    socket.addEventListener('open', () => {
      socket.send(JSON.stringify({ type: 'authenticate', access_token: getStoredAccessToken() }));
    });
    socket.addEventListener('message', (event) => {
      try {
        const payload = JSON.parse(event.data) as Record<string, unknown>;
        const eventType = typeof payload.type === 'string' ? payload.type : null;
        const eventId = typeof payload.event_id === 'string' ? payload.event_id : null;
        if (!eventType || !eventId) return;

        const nextEvent = {
          id: eventId,
          node_id: typeof payload.node_id === 'string' ? payload.node_id : null,
          event_type: eventType,
          event_payload_json: payload,
          created_at: typeof payload.created_at === 'string' ? payload.created_at : new Date().toISOString(),
        };

        queryClient.setQueryData(runQueryKeys.events(runId), (current: Array<typeof nextEvent> | undefined) => {
          const currentEvents = current ?? [];
          if (currentEvents.some((candidate) => candidate.id === eventId)) return currentEvents;
          return [...currentEvents, nextEvent];
        });

        if (eventType === 'run_completed' || eventType === 'run_failed' || eventType === 'crew_completed') {
          queryClient.invalidateQueries({ queryKey: runQueryKeys.detail(runId) });
        }
      } catch {
        // Ignore malformed stream messages; polling remains as a fallback.
      }
    });

    return () => {
      socket.close();
    };
  }, [queryClient, runId]);

  return {
    events: query.data ?? [],
    isLoading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
  };
}

export function useSubmitHumanFeedbackMutation(runId: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (body: HumanFeedbackSubmitRequest) => {
      if (!runId) {
        throw new Error('No run selected');
      }

      const response = await submitHumanFeedback(runId, body);
      if (response.error) {
        throw new Error(errorMessage(response.error, 'Failed to submit feedback'));
      }

      return requireData(response.data, 'Failed to submit feedback');
    },
    onSuccess(run) {
      queryClient.invalidateQueries({ queryKey: runQueryKeys.detail(run.id) });
      queryClient.invalidateQueries({ queryKey: runQueryKeys.events(run.id) });
    },
  });
}

const SELECTED_RUN_ID_STORAGE_KEY = 'ax:selected-run-id';

export function readSelectedRunId() {
  if (typeof window === 'undefined') {
    return null;
  }
  return window.localStorage.getItem(SELECTED_RUN_ID_STORAGE_KEY);
}

export function writeSelectedRunId(runId: string) {
  window.localStorage.setItem(SELECTED_RUN_ID_STORAGE_KEY, runId);
}
