import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

globalThis.AbortSignal = window.AbortSignal;
globalThis.AbortController = window.AbortController;

// React Flow relies on ResizeObserver in the browser; JSDOM doesn't provide it by default.
globalThis.ResizeObserver =
  globalThis.ResizeObserver ??
  (class {
    observe() {
      // no-op
    }
    unobserve() {
      // no-op
    }
    disconnect() {
      // no-op
    }
  } as unknown as typeof ResizeObserver);

class TestRequest {
  body: BodyInit | null;
  headers: Headers;
  method: string;
  signal: AbortSignal;
  url: string;

  constructor(input: RequestInfo | URL, init: RequestInit = {}) {
    this.url = typeof input === 'string' ? input : input.toString();
    this.method = (init.method ?? 'GET').toUpperCase();
    this.headers = new Headers(init.headers);
    this.body = init.body ?? null;
    this.signal = init.signal ?? new AbortController().signal;
  }

  clone() {
    return new TestRequest(this.url, {
      body: this.body,
      headers: this.headers,
      method: this.method,
      signal: this.signal,
    });
  }
}

globalThis.Request = TestRequest as typeof Request;
