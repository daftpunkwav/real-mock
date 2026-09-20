/**
 * @file prepCoachHttp.test.ts
 * @description prepCoachHttp against the real base layer: REST path/body
 * conventions, the full SSE event dispatch of `prepMessageStream` (token /
 * thinking / status / tool_step / search_results / ask_user / usage /
 * compaction / done), non-2xx envelope propagation, and the idle-watchdog
 * stall path (NET0006).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { prepCoachHttp, type PrepStreamCallbacks } from "../api/prepCoachHttp";

const BACKEND = "http://localhost:8081";

// prepMessageStream drives its idle watchdog via window.setInterval; in the
// node test environment `window` is undefined, so point it at the globals the
// fake timers patch. Re-stubbed per test: afterEach unstubbing clears it.
beforeEach(() => {
  vi.stubGlobal("window", globalThis);
});

function sseResponse(events: unknown[]): Response {
  const encoder = new TextEncoder();
  const payload = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(payload));
      controller.close();
    },
  });
  return new Response(stream);
}

function stubFetch(makeRes: () => Response): ReturnType<typeof vi.fn> {
  // A fresh Response per call: a body (and its stream) can only be read once.
  const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(makeRes()));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function hangingStreamFetch(): ReturnType<typeof vi.fn> {
  return vi.fn(
    (_url: string, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () =>
          reject(new DOMException("The operation was aborted.", "AbortError")),
        );
      }),
  );
}

function makeCallbacks() {
  const calls: Record<string, unknown[]> = {};
  const callbacks: PrepStreamCallbacks = {
    onToken: (t) => (calls.token ??= []).push(t),
    onThinking: (t) => (calls.thinking ??= []).push(t),
    onSearchResults: (g) => (calls.search ??= []).push(g),
    onStatus: (t) => (calls.status ??= []).push(t),
    onToolStep: (s) => (calls.tool ??= []).push(s),
    onAskUser: (d) => (calls.ask ??= []).push(d),
    onUsage: (u) => (calls.usage ??= []).push(u),
    onCompaction: (c) => (calls.compaction ??= []).push(c),
  };
  return { calls, callbacks };
}

function lastCall(fetchMock: ReturnType<typeof vi.fn>): { url: string; init: RequestInit } {
  const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1] as [string, RequestInit];
  return { url, init };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("prepCoachHttp REST conventions", () => {
  it("creates sessions, forks, links, archives and purges with the documented bodies", async () => {
    const fetchMock = stubFetch(() => new Response(JSON.stringify({ id: 1 })));

    await prepCoachHttp.createPrepSession({ target_role: "fe" });
    expect(lastCall(fetchMock)).toMatchObject({
      url: `${BACKEND}/api/v1/prep/sessions`,
      init: expect.objectContaining({ method: "POST" }),
    });
    expect(lastCall(fetchMock).init.body).toBe(JSON.stringify({ target_role: "fe" }));

    await prepCoachHttp.forkSession(3, 7);
    expect(lastCall(fetchMock).init.body).toBe(JSON.stringify({ up_to: 7 }));

    await prepCoachHttp.linkSession(3, null);
    expect(lastCall(fetchMock).init).toMatchObject({ method: "PUT" });
    expect(lastCall(fetchMock).init.body).toBe(JSON.stringify({ linked_session_id: null }));

    await prepCoachHttp.archiveSession(3, true);
    expect(lastCall(fetchMock).init).toMatchObject({ method: "PATCH" });
    expect(lastCall(fetchMock).init.body).toBe(JSON.stringify({ archived: true }));

    await prepCoachHttp.purgeAllSessions();
    expect(lastCall(fetchMock).init.body).toBe(JSON.stringify({ confirm: true }));

    await prepCoachHttp.purgeEmptySessions();
    expect(lastCall(fetchMock).init.body).toBeUndefined();
  });

  it("adds expected_message_count only when a number is given", async () => {
    const fetchMock = stubFetch(() => new Response(JSON.stringify({})));

    await prepCoachHttp.updateSummary(4, "sum", 12);
    expect(lastCall(fetchMock).init.body).toBe(
      JSON.stringify({ text: "sum", expected_message_count: 12 }),
    );

    await prepCoachHttp.updateSummary(4, "sum");
    expect(lastCall(fetchMock).init.body).toBe(JSON.stringify({ text: "sum" }));

    await prepCoachHttp.truncateMessages(4, 2, 9);
    expect(lastCall(fetchMock).init.body).toBe(
      JSON.stringify({ from_index: 2, expected_message_count: 9 }),
    );

    await prepCoachHttp.truncateMessages(4, 2);
    expect(lastCall(fetchMock).init.body).toBe(JSON.stringify({ from_index: 2 }));
  });
});

describe("prepMessageStream SSE dispatch", () => {
  it("routes every event type to its callback and aggregates the done payload", async () => {
    const done = {
      type: "done",
      token_usage: 42,
      prompt_tokens: 100,
      completion_tokens: 50,
      cached_tokens: 60,
      prompt_tokens_estimated: 1,
      turn_id: "turn-1",
      prefix_fingerprint: "fp-1",
      message_count: 8,
    };
    const fetchMock = stubFetch(() =>
      sseResponse([
        { type: "token", content: "Hel" },
        { type: "token", content: "lo" },
        { type: "thinking", content: "hmm" },
        { type: "status", text: "searching" },
        {
          type: "tool_step",
          name: "web_search",
          query: "q",
          args: { k: 1 },
          result: "r",
        },
        { type: "search_results", groups: [{ id: "g" }] },
        { type: "ask_user", question: "pick one", options: ["a", "b"] },
        {
          type: "usage",
          prompt_tokens: 100,
          completion_tokens: 50,
          cached_tokens: 60,
        },
        {
          type: "compaction",
          before: 10,
          after: 4,
          summarized: true,
          prompt_tokens: 1,
          completion_tokens: 2,
          latency_ms: 5,
        },
        done,
      ]),
    );
    const { calls, callbacks } = makeCallbacks();

    const result = await prepCoachHttp.prepMessageStream(1, "hi", callbacks);

    expect(calls.token).toEqual(["Hel", "lo"]);
    expect(calls.thinking).toEqual(["hmm"]);
    expect(calls.status).toEqual(["searching"]);
    expect(calls.tool).toEqual([
      { name: "web_search", query: "q", args: { k: 1 }, result: "r" },
    ]);
    expect(calls.search).toEqual([[{ id: "g" }]]);
    expect(calls.ask).toEqual([expect.objectContaining({ question: "pick one" })]);
    expect(calls.usage).toEqual([
      { prompt_tokens: 100, completion_tokens: 50, cached_tokens: 60 },
    ]);
    expect(calls.compaction).toEqual([
      {
        before: 10,
        after: 4,
        summarized: true,
        prompt_tokens: 1,
        completion_tokens: 2,
        latency_ms: 5,
      },
    ]);
    expect(result).toEqual({
      token_usage: 42,
      prompt_tokens: 100,
      completion_tokens: 50,
      cached_tokens: 60,
      prompt_tokens_estimated: 1,
      turn_id: "turn-1",
      prefix_fingerprint: "fp-1",
      message_count: 8,
      usage: { prompt_tokens: 100, completion_tokens: 50, cached_tokens: 60 },
    });

    // Stream POST hits the session-scoped stream path with credentials.
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BACKEND}/api/v1/prep/sessions/1/message/stream`);
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
  });

  it("sends only defined stream options", async () => {
    let captured: RequestInit | undefined;
    const fetchMock = vi.fn().mockImplementation(async (_url: string, init: RequestInit) => {
      captured = init;
      return sseResponse([{ type: "done" }]);
    });
    vi.stubGlobal("fetch", fetchMock);

    await prepCoachHttp.prepMessageStream(2, "hi", makeCallbacks().callbacks, {
      modelProfileId: 5,
      dropLastAssistant: false,
      uiLocale: "",
      compactThreshold: null,
      contextSessionIds: [],
    });

    expect(JSON.parse(captured!.body as string)).toEqual({
      content: "hi",
      model_profile_id: 5,
    });
  });

  it("propagates the structured error envelope on non-2xx", async () => {
    stubFetch(
      () =>
        new Response(JSON.stringify({ error: { code: "A0002", message: "slow down" } }), {
          status: 429,
        }),
    );
    const err = await prepCoachHttp
      .prepMessageStream(1, "hi", makeCallbacks().callbacks)
      .catch((e) => e);
    expect(err).toMatchObject({ status: 429, code: "A0002", message: "slow down" });
  });

  it("maps a failed connection to NET0000", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("down")));
    const err = await prepCoachHttp
      .prepMessageStream(1, "hi", makeCallbacks().callbacks)
      .catch((e) => e);
    expect(err).toMatchObject({ code: "NET0000" });
  });

  it("converts an idle-watchdog abort into NET0006 instead of a raw abort", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", hangingStreamFetch());
    const pending = prepCoachHttp.prepMessageStream(1, "hi", makeCallbacks().callbacks);
    const pendingAssert = expect(pending).rejects.toMatchObject({ code: "NET0006" });
    // The watchdog polls every 5s against a 120s idle budget.
    await vi.advanceTimersByTimeAsync(130_000);
    await pendingAssert;
  });
});
