import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, test, expect, vi } from 'vitest';
import { useFlowRunStream } from '../../src/features/runs/useFlowRunStream';

vi.mock('../../src/api/runs', () => ({
  flowRunStreamUrl: (runId: string) => `ws://localhost/api/flow-runs/${runId}/stream`,
}));

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  close() {
    this.onclose?.();
    return undefined;
  }

  send() {
    return undefined;
  }

  emitMessage(payload: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
  }

  emitClose() {
    this.onclose?.();
  }

  emitError() {
    this.onerror?.();
  }
}

function StreamProbe({
  onEvent,
  onHitlRequested,
}: {
  onEvent?: (event: Record<string, unknown>) => void;
  onHitlRequested: () => void;
}) {
  useFlowRunStream({
    runId: 'run-123',
    enabled: true,
    onEvent,
    onHitlRequested,
  });
  return null;
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.stubGlobal('WebSocket', FakeWebSocket);
});

afterEach(() => {
  vi.useRealTimers();
});

test('keeps the same WebSocket when only the HITL callback changes', () => {
  const firstCallback = vi.fn();
  const secondCallback = vi.fn();
  const { rerender } = render(<StreamProbe onHitlRequested={firstCallback} />);

  expect(FakeWebSocket.instances).toHaveLength(1);

  rerender(<StreamProbe onHitlRequested={secondCallback} />);

  expect(FakeWebSocket.instances).toHaveLength(1);
  FakeWebSocket.instances[0].emitMessage({ type: 'hitl_requested' });
  expect(firstCallback).not.toHaveBeenCalled();
  expect(secondCallback).toHaveBeenCalledTimes(1);
});

test('ignores duplicate HITL stream events with the same event id', () => {
  const onHitlRequested = vi.fn();
  render(<StreamProbe onHitlRequested={onHitlRequested} />);

  FakeWebSocket.instances[0].emitMessage({ type: 'hitl_requested', event_id: 'event-1' });
  FakeWebSocket.instances[0].emitMessage({ type: 'hitl_requested', event_id: 'event-1' });

  expect(onHitlRequested).toHaveBeenCalledTimes(1);
});

test('passes non-HITL stream events to the generic event callback', () => {
  const onEvent = vi.fn();
  const onHitlRequested = vi.fn();
  render(<StreamProbe onEvent={onEvent} onHitlRequested={onHitlRequested} />);

  const payload = {
    type: 'collaboration_started',
    event_id: 'event-2',
    run_id: 'run-123',
  };
  FakeWebSocket.instances[0].emitMessage(payload);

  expect(onEvent).toHaveBeenCalledWith(payload);
  expect(onHitlRequested).not.toHaveBeenCalled();
});

test('reconnects with a replacement WebSocket after stream close or error while enabled', () => {
  vi.useFakeTimers();
  const onHitlRequested = vi.fn();
  render(<StreamProbe onHitlRequested={onHitlRequested} />);

  expect(FakeWebSocket.instances).toHaveLength(1);

  act(() => {
    FakeWebSocket.instances[0].emitClose();
    vi.advanceTimersByTime(500);
  });

  expect(FakeWebSocket.instances).toHaveLength(2);
  FakeWebSocket.instances[1].onopen?.();

  act(() => {
    FakeWebSocket.instances[1].emitError();
    vi.advanceTimersByTime(1_000);
  });

  expect(FakeWebSocket.instances).toHaveLength(3);
});

test('ignores stale stream close or error after a replacement socket opens', () => {
  vi.useFakeTimers();
  const onEvent = vi.fn();
  const onHitlRequested = vi.fn();
  render(<StreamProbe onEvent={onEvent} onHitlRequested={onHitlRequested} />);

  const staleSocket = FakeWebSocket.instances[0];
  act(() => {
    staleSocket.emitClose();
    vi.advanceTimersByTime(500);
  });

  expect(FakeWebSocket.instances).toHaveLength(2);
  FakeWebSocket.instances[1].onopen?.();

  act(() => {
    staleSocket.emitError();
    staleSocket.emitClose();
    vi.advanceTimersByTime(5_000);
  });

  expect(FakeWebSocket.instances).toHaveLength(2);
  staleSocket.emitMessage({ type: 'collaboration_started', event_id: 'stale-event' });
  expect(onEvent).not.toHaveBeenCalled();
});

test('stops reconnecting after repeated short-lived stream connections', () => {
  vi.useFakeTimers();
  const onHitlRequested = vi.fn();
  render(<StreamProbe onHitlRequested={onHitlRequested} />);

  const reconnectDelays = [500, 1_000, 2_000, 4_000, 5_000];
  reconnectDelays.forEach((delay, index) => {
    FakeWebSocket.instances[index].onopen?.();
    act(() => {
      FakeWebSocket.instances[index].emitClose();
      vi.advanceTimersByTime(delay);
    });
    expect(FakeWebSocket.instances).toHaveLength(index + 2);
  });

  FakeWebSocket.instances[5].onopen?.();
  act(() => {
    FakeWebSocket.instances[5].emitClose();
    vi.advanceTimersByTime(10_000);
  });

  expect(FakeWebSocket.instances).toHaveLength(6);
});

test('does not reconnect after the stream hook is unmounted', () => {
  vi.useFakeTimers();
  const onHitlRequested = vi.fn();
  const { unmount } = render(<StreamProbe onHitlRequested={onHitlRequested} />);

  expect(FakeWebSocket.instances).toHaveLength(1);

  unmount();

  act(() => {
    FakeWebSocket.instances[0].emitClose();
    vi.advanceTimersByTime(5_000);
  });

  expect(FakeWebSocket.instances).toHaveLength(1);
});
