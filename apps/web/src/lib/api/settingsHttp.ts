/** Provider / model-entry REST client. */

import type { LLMTestResponse } from "@/lib/api/contract";
import { request } from "@/lib/api/base";

export const settingsHttp = {
  listModelOptions: () =>
    request<{ models: import("@/types").ModelProfile[] }>("/v1/settings/models"),
  listProviders: () =>
    request<{ providers: import("@/types").ProviderWithModels[] }>("/v1/settings/providers"),
  createProvider: (data: import("@/types").ProviderWrite) =>
    request<{ id: number }>("/v1/settings/providers", { method: "POST", body: JSON.stringify(data) }),
  updateProvider: (id: number, data: import("@/types").ProviderWrite) =>
    request<{ id: number }>(`/v1/settings/providers/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteProvider: (id: number) =>
    request<{ deleted: number }>(`/v1/settings/providers/${id}`, { method: "DELETE" }),
  listRecommendedVendors: () =>
    request<{ vendors: import("@/types").RecommendedVendor[] }>("/v1/settings/vendors"),
  createModel: (providerId: number, data: import("@/types").ModelProfileWrite) =>
    request<import("@/types").ModelProfile>(`/v1/settings/providers/${providerId}/models`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateModel: (id: number, data: Partial<import("@/types").ModelProfileWrite>) =>
    request<import("@/types").ModelProfile>(`/v1/settings/models/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteModel: (id: number) =>
    request<{ deleted: number }>(`/v1/settings/models/${id}`, { method: "DELETE" }),
  testModel: (id: number) =>
    request<LLMTestResponse>(`/v1/settings/test/model/${id}`, { method: "POST" }),
  getBindings: () =>
    request<import("@/types").TaskBindings>("/v1/settings/bindings"),
  updateBinding: (
    task: "chat" | "stt" | "tts",
    data: { profile_id: number; fallback_handler?: string; fallback_mode?: string },
  ) =>
    request<import("@/types").TaskBindings>(`/v1/settings/bindings/${task}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  githubStatus: () =>
    request<{ configured: boolean; tail: string }>("/v1/settings/integrations/github"),
  saveGithubToken: (token: string) =>
    request<{ configured: boolean; tail: string }>("/v1/settings/integrations/github", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),
  clearGithubToken: () =>
    request<{ configured: boolean; tail: string }>("/v1/settings/integrations/github", {
      method: "DELETE",
    }),
  testGithubToken: (token?: string) =>
    request<{
      ok: boolean;
      message?: string;
      status?: number;
      limit?: number;
      remaining?: number;
      reset_in?: number;
      authenticated?: boolean;
    }>("/v1/settings/integrations/github/test", {
      method: "POST",
      body: JSON.stringify(token ? { token } : {}),
    }),
};
