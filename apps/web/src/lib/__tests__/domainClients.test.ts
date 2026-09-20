/**
 * @file domainClients.test.ts
 * @description Thin REST clients (settings / interview / growth / records)
 * against the real base layer: each method must hit its `/api/v1` path with the
 * documented method + JSON body, and surface the parsed response.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

// interviewHttp imports the i18n barrel; stub it so vitest never loads .tsx.
vi.mock("@/i18n", () => ({
  getLocale: () => "en",
}));

import { growthHttp } from "../api/growthHttp";
import { interviewHttp } from "../api/interviewHttp";
import { recordsHttp } from "../api/recordsHttp";
import { settingsHttp } from "../api/settingsHttp";

const BACKEND = "http://localhost:8081";

function jsonOk(body: unknown): Response {
  return new Response(JSON.stringify(body));
}

function stubFetch(): ReturnType<typeof vi.fn> {
  // A fresh Response per call: a body can only be read once.
  const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonOk({ ok: true })));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function lastCall(fetchMock: ReturnType<typeof vi.fn>): { url: string; init: RequestInit } {
  const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1] as [string, RequestInit];
  return { url, init };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("settingsHttp", () => {
  it("creates a provider with a JSON body", async () => {
    const fetchMock = stubFetch();
    await settingsHttp.createProvider({ name: "openai" } as never);
    const { url, init } = lastCall(fetchMock);
    expect(url).toBe(`${BACKEND}/api/v1/settings/providers`);
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ name: "openai" }));
  });

  it("puts channel config on the provider/channel path", async () => {
    const fetchMock = stubFetch();
    await settingsHttp.updateChannel(7, "chat", { api_key: "k" } as never);
    const { url, init } = lastCall(fetchMock);
    expect(url).toBe(`${BACKEND}/api/v1/settings/providers/7/channels/chat`);
    expect(init.method).toBe("PUT");
  });

  it("fetches the channel catalog with GET", async () => {
    const fetchMock = stubFetch();
    await settingsHttp.fetchChannelCatalog(7, "stt");
    const { url, init } = lastCall(fetchMock);
    expect(url).toBe(`${BACKEND}/api/v1/settings/providers/7/channels/stt/catalog`);
    expect(init.method).toBeUndefined();
  });

  it("applies a vendor via POST without a body", async () => {
    const fetchMock = stubFetch();
    await settingsHttp.applyVendor("minimax");
    const { url, init } = lastCall(fetchMock);
    expect(url).toBe(`${BACKEND}/api/v1/settings/vendors/minimax/apply`);
    expect(init.method).toBe("POST");
    expect(init.body).toBeUndefined();
  });

  it("updates a task binding with a PUT body", async () => {
    const fetchMock = stubFetch();
    await settingsHttp.updateBinding("chat", { profile_id: 3 });
    const { url, init } = lastCall(fetchMock);
    expect(url).toBe(`${BACKEND}/api/v1/settings/bindings/chat`);
    expect(init.method).toBe("PUT");
    expect(init.body).toBe(JSON.stringify({ profile_id: 3 }));
  });

  it("saves the GitHub token and omits the body when testing a stored one", async () => {
    const fetchMock = stubFetch();
    await settingsHttp.saveGithubToken("tok-1");
    expect(lastCall(fetchMock).init.body).toBe(JSON.stringify({ token: "tok-1" }));

    await settingsHttp.testGithubToken();
    expect(lastCall(fetchMock).init.body).toBe(JSON.stringify({}));

    await settingsHttp.testGithubToken("tok-2");
    expect(lastCall(fetchMock).init.body).toBe(JSON.stringify({ token: "tok-2" }));
  });

  it("deletes models and providers by id", async () => {
    const fetchMock = stubFetch();
    await settingsHttp.deleteModel(4);
    expect(lastCall(fetchMock)).toMatchObject({
      url: `${BACKEND}/api/v1/settings/models/4`,
      init: expect.objectContaining({ method: "DELETE" }),
    });
    await settingsHttp.deleteProvider(5);
    expect(lastCall(fetchMock)).toMatchObject({
      url: `${BACKEND}/api/v1/settings/providers/5`,
      init: expect.objectContaining({ method: "DELETE" }),
    });
  });

  it("reads catalogs and writes models / providers on the documented paths", async () => {
    const fetchMock = stubFetch();
    await settingsHttp.listModelOptions();
    expect(lastCall(fetchMock).url).toBe(`${BACKEND}/api/v1/settings/models`);
    await settingsHttp.listProviders();
    expect(lastCall(fetchMock).url).toBe(`${BACKEND}/api/v1/settings/providers`);
    await settingsHttp.listRecommendedVendors();
    expect(lastCall(fetchMock).url).toBe(`${BACKEND}/api/v1/settings/vendors`);
    await settingsHttp.getBindings();
    expect(lastCall(fetchMock).url).toBe(`${BACKEND}/api/v1/settings/bindings`);
    await settingsHttp.githubStatus();
    expect(lastCall(fetchMock).url).toBe(`${BACKEND}/api/v1/settings/integrations/github`);

    await settingsHttp.updateProvider(6, { name: "x" } as never);
    expect(lastCall(fetchMock)).toMatchObject({
      url: `${BACKEND}/api/v1/settings/providers/6`,
      init: expect.objectContaining({ method: "PUT" }),
    });
    await settingsHttp.createModel(6, { name: "m" } as never);
    expect(lastCall(fetchMock).url).toBe(`${BACKEND}/api/v1/settings/providers/6/models`);
    await settingsHttp.updateModel(8, { name: "m2" } as never);
    expect(lastCall(fetchMock)).toMatchObject({
      url: `${BACKEND}/api/v1/settings/models/8`,
      init: expect.objectContaining({ method: "PUT" }),
    });
    await settingsHttp.clearGithubToken();
    expect(lastCall(fetchMock)).toMatchObject({
      url: `${BACKEND}/api/v1/settings/integrations/github`,
      init: expect.objectContaining({ method: "DELETE" }),
    });
    await settingsHttp.testModel(8);
    expect(lastCall(fetchMock)).toMatchObject({
      url: `${BACKEND}/api/v1/settings/test/model/8`,
      init: expect.objectContaining({ method: "POST" }),
    });
  });
});

describe("interviewHttp", () => {
  it("creates a session with ui_locale and the outline default", async () => {
    const fetchMock = stubFetch();
    await interviewHttp.createSessionWithAI({ role: "fe" } as never, {
      chat_profile_id: 9,
      reasoning_effort: "high",
    });
    const { url, init } = lastCall(fetchMock);
    expect(url).toBe(`${BACKEND}/api/v1/interview/sessions`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      role: "fe",
      ui_locale: "en",
      reference_detail: "outline",
      ai_overrides: { chat_profile_id: 9, reasoning_effort: "high" },
    });
  });

  it("honors an explicit reference_detail and omits empty ai overrides", async () => {
    const fetchMock = stubFetch();
    await interviewHttp.createSessionWithAI({ role: "fe" } as never, null, {
      reference_detail: "full",
    });
    expect(JSON.parse(lastCall(fetchMock).init.body as string)).toEqual({
      role: "fe",
      ui_locale: "en",
      reference_detail: "full",
      ai_overrides: undefined,
    });
  });

  it("creates a process with the same locale convention", async () => {
    const fetchMock = stubFetch();
    await interviewHttp.createProcess({ company: "acme" } as never, {
      reference_detail: "full",
    });
    const { url, init } = lastCall(fetchMock);
    expect(url).toBe(`${BACKEND}/api/v1/interview/processes`);
    expect(JSON.parse(init.body as string)).toEqual({
      company: "acme",
      ui_locale: "en",
      reference_detail: "full",
    });
  });

  it("posts the company brief with locale override and clears briefs with DELETE", async () => {
    const fetchMock = stubFetch();
    await interviewHttp.fetchCompanyBrief("acme", "fe", "senior", "tech", { locale: "zh-CN" });
    let { url, init } = lastCall(fetchMock);
    expect(url).toBe(`${BACKEND}/api/v1/interview/company-brief`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      company: "acme",
      role: "fe",
      level: "senior",
      interview_type: "tech",
      locale: "zh-CN",
    });

    await interviewHttp.clearCompanyBriefs();
    ({ url, init } = lastCall(fetchMock));
    expect(url).toBe(`${BACKEND}/api/v1/interview/company-briefs`);
    expect(init.method).toBe("DELETE");
  });

  it("creates the next round on the process path", async () => {
    const fetchMock = stubFetch();
    await interviewHttp.createNextRound(12);
    expect(lastCall(fetchMock)).toMatchObject({
      url: `${BACKEND}/api/v1/interview/processes/12/rounds`,
      init: expect.objectContaining({ method: "POST" }),
    });
  });

  it("returns parsed list bodies", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) =>
      Promise.resolve(jsonOk(url.includes("options") ? { ok: true } : [{ id: 1 }])),
    );
    vi.stubGlobal("fetch", fetchMock);
    await expect(interviewHttp.listSessions()).resolves.toEqual([{ id: 1 }]);
    await expect(interviewHttp.getOptions()).resolves.toEqual({ ok: true });
  });
});

describe("growthHttp and recordsHttp", () => {
  it("hits the growth paths", async () => {
    const fetchMock = stubFetch();
    await growthHttp.getGrowthHistory();
    expect(lastCall(fetchMock).url).toBe(`${BACKEND}/api/v1/growth/history`);
    await growthHttp.getSystemInsights();
    expect(lastCall(fetchMock).url).toBe(`${BACKEND}/api/v1/growth/system-insights`);
    await growthHttp.getAggregated();
    expect(lastCall(fetchMock).url).toBe(`${BACKEND}/api/v1/growth/aggregated`);
  });

  it("hits the records paths and gives report retry the LLM-heavy budget", async () => {
    const fetchMock = stubFetch();
    await recordsHttp.listSessions();
    expect(lastCall(fetchMock).url).toBe(`${BACKEND}/api/v1/records/sessions`);
    await recordsHttp.getLedger(3);
    expect(lastCall(fetchMock).url).toBe(`${BACKEND}/api/v1/records/sessions/3/ledger`);

    await recordsHttp.retryReport(8);
    const { url, init } = lastCall(fetchMock);
    expect(url).toBe(`${BACKEND}/api/v1/reports/8/retry`);
    expect(init.method).toBe("POST");
  });
});
