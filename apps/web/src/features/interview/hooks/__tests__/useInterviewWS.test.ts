// @vitest-environment jsdom
/**
 * Contract tests for useInterviewWS using a programmable MockWebSocket.
 *
 * Verifies the client behavior required by `/api/v1/ws/interview/{id}`:
 * URL and connection state, server_ping/pong, turn_state tracking, event dispatch,
 * malformed-frame tolerance, backoff reconnects, clean closes, exhausted retries,
 * and unmount cleanup.
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useInterviewWS, type WSHandlers } from "../useInterviewWS";

vi.mock("@/lib/env", () => ({
  getEnv: () => ({
    API_BASE: "http://test-host",
    WS_BASE: "ws://test-host",
    STREAM_API_BASE: "http://test-host",
  }),
}));

type CloseInfo = { code: number; reason: string };

class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances: MockWebSocket[] = [];

  url: string;
  readyState = MockWebSocket.CONNECTING;
  sent: string[] = [];
  closedCodes: CloseInfo[] = [];
  onopen: ((ev?: unknown) => void) | null = null;
  onclose: ((ev: CloseInfo) => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(code = 1000, reason = ""): void {
    if (this.readyState === MockWebSocket.CLOSED) return;
    this.readyState = MockWebSocket.CLOSED;
    this.closedCodes.push({ code, reason });
    // Browsers dispatch onclose asynchronously.
    queueMicrotask(() => this.onclose?.({ code, reason }));
  }

  /** Complete the server-side handshake in a test. */
  serverOpen(): void {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.();
  }

  /** Deliver a JSON frame from the server in a test. */
  serverMessage(frame: unknown): void {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }

  /** Simulate an abnormal server-side disconnect. */
  serverClose(code: number, reason = ""): void {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code, reason });
  }
}

const REAL_WS = globalThis.WebSocket;

beforeEach(() => {
  vi.useFakeTimers();
  MockWebSocket.instances = [];
  vi.stubGlobal("WebSocket", MockWebSocket);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  (globalThis as { WebSocket: unknown }).WebSocket = REAL_WS;
});

function lastSocket(): MockWebSocket {
  const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
  if (!ws) throw new Error("no MockWebSocket instance");
  return ws;
}

async function mount(sessionId = 7, handlers?: WSHandlers, options?: { maxRetries?: number }) {
  const rendered = renderHook(() => useInterviewWS(sessionId, handlers, options));
  await act(async () => {});
  return rendered;
}

describe("useInterviewWS contract", () => {
  it("builds the WebSocket URL from sessionId and opens after handshake", async () => {
    const { result } = await mount();
    expect(result.current.connectionState).toBe("connecting");
    expect(lastSocket().url).toBe("ws://test-host/api/v1/ws/interview/7");

    act(() => lastSocket().serverOpen());
    expect(result.current.connected).toBe(true);
    expect(result.current.everConnected).toBe(true);
    expect(result.current.connectionState).toBe("open");
  });

  it("automatically replies to server_ping with the same timestamp", async () => {
    await mount();
    const ws = lastSocket();
    act(() => {
      ws.serverOpen();
      ws.serverMessage({ type: "server_ping", t: 42 });
    });
    expect(ws.sent).toEqual([JSON.stringify({ type: "pong", t: 42 })]);
  });

  it("synchronizes turn_state events to turnState", async () => {
    const { result } = await mount();
    act(() => {
      lastSocket().serverOpen();
      lastSocket().serverMessage({ type: "turn_state", state: "AI_SPEAKING" });
    });
    expect(result.current.turnState).toBe("AI_SPEAKING");
  });

  it("dispatches server events to registered handlers", async () => {
    const onToken = vi.fn();
    const { result } = await mount(7, { assistant_token: onToken });
    act(() => {
      lastSocket().serverOpen();
      lastSocket().serverMessage({ type: "assistant_token", token: "What..." });
    });
    expect(onToken).toHaveBeenCalledTimes(1);
    expect(onToken).toHaveBeenCalledWith(expect.objectContaining({ type: "assistant_token", token: "What..." }));
    expect(result.current.turnState).toBe("IDLE");
  });

  it("ignores malformed JSON frames without disconnecting", async () => {
    await mount();
    const ws = lastSocket();
    act(() => {
      ws.serverOpen();
      ws.onmessage?.({ data: "{{not-json" });
    });
    expect(ws.readyState).toBe(MockWebSocket.OPEN);
    expect(ws.sent).toEqual([]);
  });

  it("reconnects with backoff after an abnormal disconnect", async () => {
    const { result } = await mount(7, undefined, { maxRetries: 3 });
    act(() => lastSocket().serverOpen());
    act(() => lastSocket().serverClose(1011, "boom"));
    expect(result.current.connectionState).toBe("reconnecting");
    expect(result.current.reconnectAttempt).toBe(1);

    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    expect(MockWebSocket.instances.length).toBe(2);
  });

  it("does not reconnect after an intentional code 1000 close", async () => {
    await mount(7, undefined, { maxRetries: 3 });
    act(() => {
      lastSocket().serverOpen();
      lastSocket().serverClose(1000, "client_cancel");
    });
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    expect(MockWebSocket.instances.length).toBe(1);
  });

  it("marks exhausted retries failed and keeps the 20-second slow retry", async () => {
    const { result } = await mount(7, undefined, { maxRetries: 1 });
    act(() => lastSocket().serverOpen());
    // The first abnormal disconnect remains within maxRetries.
    act(() => lastSocket().serverClose(1006));
    expect(result.current.connectionState).toBe("reconnecting");
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });

    // The second disconnect exceeds maxRetries and marks the connection failed.
    act(() => lastSocket().serverClose(1006));
    expect(result.current.connectionState).toBe("failed");

    // A silent retry still runs after 20 seconds.
    await act(async () => {
      vi.advanceTimersByTime(20_000);
    });
    expect(MockWebSocket.instances.length).toBe(3);
  });

  it("returns false before open and sends JSON frames after open", async () => {
    const { result } = await mount();
    expect(result.current.send({ type: "user_text", text: "hi" })).toBe(false);

    act(() => lastSocket().serverOpen());
    expect(result.current.send({ type: "user_text", text: "hi" })).toBe(true);
    expect(lastSocket().sent).toEqual([JSON.stringify({ type: "user_text", text: "hi" })]);
  });

  it("closes with client_cancel on unmount and does not reconnect", async () => {
    const { unmount } = await mount(7, undefined, { maxRetries: 3 });
    const ws = lastSocket();
    act(() => ws.serverOpen());
    unmount();

    expect(ws.closedCodes).toContainEqual({ code: 1000, reason: "client_cancel" });
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    expect(MockWebSocket.instances.length).toBe(1);
  });
});
