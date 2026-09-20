/**
 * @file prepMemoryHttp.test.ts
 * @description prepMemoryHttp: client-side list-window clamping (server clamps
 * 1..50 anyway) plus path / method / body conventions for the memory CRUD.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { prepMemoryHttp } from "../api/prepMemoryHttp";

const BACKEND = "http://localhost:8081";

function stubFetch(body: unknown = []): ReturnType<typeof vi.fn> {
  // A fresh Response per call: a body can only be read once.
  const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify(body))));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function lastUrl(fetchMock: ReturnType<typeof vi.fn>): string {
  const [url] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1] as [string, RequestInit];
  return url;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("prepMemoryHttp.listMemories clamping", () => {
  it.each([
    ["omitted limit → default 20", undefined, 20],
    ["NaN limit → default 20", Number.NaN, 20],
    ["zero limit clamps to floor 1", 0, 1],
    ["over-range limit → cap 50", 99, 50],
    ["negative limit → floor 1", -5, 1],
    ["fractional limit → floored", 30.7, 30],
    ["in-range limit kept", 7, 7],
  ])("%s", (_name, limit, expected) => {
    const fetchMock = stubFetch();
    prepMemoryHttp.listMemories(undefined, limit as number | undefined);
    expect(lastUrl(fetchMock)).toBe(`${BACKEND}/api/v1/prep/memories?limit=${expected}`);
  });

  it("encodes the tag filter alongside the limit", () => {
    const fetchMock = stubFetch();
    prepMemoryHttp.listMemories("system design", 5);
    expect(lastUrl(fetchMock)).toContain("tag=system+design");
    expect(lastUrl(fetchMock)).toContain("limit=5");
  });
});

describe("prepMemoryHttp CRUD", () => {
  it("creates from a rating with a JSON body", async () => {
    const fetchMock = stubFetch({ id: 1 });
    const body = { user_input: "q", agent_output: "a", score: 5 };
    await prepMemoryHttp.createFromRating(body);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BACKEND}/api/v1/prep/memories`);
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify(body));
  });

  it("patches and deletes by id", async () => {
    const fetchMock = stubFetch({ id: 2 });
    await prepMemoryHttp.update(2, { score: null, tags: ["a"] });
    let [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BACKEND}/api/v1/prep/memories/2`);
    expect(init.method).toBe("PATCH");
    expect(init.body).toBe(JSON.stringify({ score: null, tags: ["a"] }));

    await prepMemoryHttp.remove(2);
    [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe(`${BACKEND}/api/v1/prep/memories/2`);
    expect(init.method).toBe("DELETE");
  });

  it("posts batch deletion with the id list", async () => {
    const fetchMock = stubFetch({ deleted: 2 });
    await prepMemoryHttp.batchRemove([1, 2]);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BACKEND}/api/v1/prep/memories/batch-delete`);
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ ids: [1, 2] }));
  });

  it("lists tags and fetches detail by id", async () => {
    const fetchMock = stubFetch({ tags: ["x"] });
    await prepMemoryHttp.listTags();
    expect(lastUrl(fetchMock)).toBe(`${BACKEND}/api/v1/prep/memories/tags`);
    await prepMemoryHttp.getDetail(9);
    expect(lastUrl(fetchMock)).toBe(`${BACKEND}/api/v1/prep/memories/9`);
  });
});
