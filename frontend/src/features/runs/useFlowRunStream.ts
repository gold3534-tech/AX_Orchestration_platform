import { useEffect, useRef } from 'react';

import { flowRunStreamUrl } from '../../api/runs';
import { getStoredAccessToken } from '../../hooks/useAuth';

const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_BASE_DELAY_MS = 500;
const RECONNECT_MAX_DELAY_MS = 5_000;
const STABLE_CONNECTION_MS = 30_000;

type FlowRunStreamOptions = {
  runId: string | undefined;
  enabled: boolean;
  onEvent?: (event: Record<string, unknown>) => void;
  onHitlRequested: () => void;
};

export function useFlowRunStream({ runId, enabled, onEvent, onHitlRequested }: FlowRunStreamOptions) {
  const onEventRef = useRef(onEvent);
  const onHitlRequestedRef = useRef(onHitlRequested);
  const handledHitlEventIdsRef = useRef(new Set<string>());

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    onHitlRequestedRef.current = onHitlRequested;
  }, [onHitlRequested]);

  useEffect(() => {
    if (!enabled || !runId || typeof WebSocket === 'undefined') {
      return undefined;
    }

    let isActive = true;
    let reconnectAttempts = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let stableConnectionTimer: ReturnType<typeof setTimeout> | null = null;
    let socket: WebSocket | null = null;
    const streamRunId = runId;
    handledHitlEventIdsRef.current.clear();

    function clearReconnectTimer() {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    }

    function clearStableConnectionTimer() {
      if (stableConnectionTimer) {
        clearTimeout(stableConnectionTimer);
        stableConnectionTimer = null;
      }
    }

    function scheduleReconnect() {
      if (!isActive || reconnectTimer || reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        return;
      }

      const delayMs = Math.min(RECONNECT_BASE_DELAY_MS * 2 ** reconnectAttempts, RECONNECT_MAX_DELAY_MS);
      reconnectAttempts += 1;
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        if (isActive) {
          openSocket();
        }
      }, delayMs);
    }

    function openSocket() {
      clearStableConnectionTimer();
      const nextSocket = new WebSocket(flowRunStreamUrl(streamRunId));
      socket = nextSocket;

      nextSocket.onopen = () => {
        if (!isActive || socket !== nextSocket) {
          return;
        }
        clearStableConnectionTimer();
        stableConnectionTimer = setTimeout(() => {
          if (isActive && socket === nextSocket) {
            reconnectAttempts = 0;
          }
        }, STABLE_CONNECTION_MS);
        const accessToken = getStoredAccessToken();
        if (accessToken) {
          nextSocket.send(JSON.stringify({ type: 'authenticate', access_token: accessToken }));
        }
      };

      nextSocket.onmessage = (event) => {
        if (!isActive || socket !== nextSocket) {
          return;
        }
        try {
          const payload = JSON.parse(event.data) as { event_id?: string; type?: string };
          onEventRef.current?.(payload as Record<string, unknown>);
          if (payload.type === 'hitl_requested') {
            if (payload.event_id) {
              if (handledHitlEventIdsRef.current.has(payload.event_id)) {
                return;
              }
              handledHitlEventIdsRef.current.add(payload.event_id);
            }
            onHitlRequestedRef.current();
          }
        } catch {
          return;
        }
      };

      nextSocket.onclose = () => {
        if (!isActive || socket !== nextSocket) {
          return;
        }
        clearStableConnectionTimer();
        scheduleReconnect();
      };
      nextSocket.onerror = () => {
        if (!isActive || socket !== nextSocket) {
          return;
        }
        clearStableConnectionTimer();
        scheduleReconnect();
      };
    }

    openSocket();

    return () => {
      isActive = false;
      clearReconnectTimer();
      clearStableConnectionTimer();
      socket?.close();
    };
  }, [enabled, runId]);
}
