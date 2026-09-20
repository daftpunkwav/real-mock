/**
 * @file prepMemoryHttp.ts
 * @description Prep long-term memory REST client (list/edit/delete rated turns
 * and agent notes for the settings memory panel and the rating flow).
 */

import type { PrepMemoryDetail, PrepMemorySummary } from "@/lib/api/contract";
import { request } from "@/lib/api/base";

export interface PrepMemoryCreateBody {
  session_id?: number;
  user_input: string;
  agent_output: string;
  score?: number;
  reasons?: string[];
  comment?: string;
  tags?: string[];
  origin?: string;
}

export interface PrepMemoryUpdateBody {
  summary?: string;
  tags?: string[];
  comment?: string;
  score?: number | null;
}

/** Client-side mirror of the server list window (server clamps 1..50). */
const MEMORY_LIST_LIMIT = 50;
const MEMORY_LIST_DEFAULT = 20;

export const prepMemoryHttp = {
  listMemories: (tag?: string, limit?: number) => {
    const params = new URLSearchParams();
    if (tag) params.set("tag", tag);
    // Non-number limits fall back to the default; finite values clamp into
    // 1..50 (the server clamps anyway).
    const clamped =
      typeof limit === "number" && Number.isFinite(limit)
        ? Math.min(Math.max(Math.floor(limit), 1), MEMORY_LIST_LIMIT)
        : MEMORY_LIST_DEFAULT;
    params.set("limit", String(clamped));
    const suffix = params.size > 0 ? `?${params.toString()}` : "";
    return request<PrepMemorySummary[]>(`/v1/prep/memories${suffix}`);
  },
  listTags: () => request<{ tags: string[] }>("/v1/prep/memories/tags"),
  getDetail: (id: number) => request<PrepMemoryDetail>(`/v1/prep/memories/${id}`),
  createFromRating: (data: PrepMemoryCreateBody) =>
    request<PrepMemoryDetail>("/v1/prep/memories", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: number, data: PrepMemoryUpdateBody) =>
    request<PrepMemoryDetail>(`/v1/prep/memories/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  remove: (id: number) =>
    request<{ deleted: number }>(`/v1/prep/memories/${id}`, { method: "DELETE" }),
  batchRemove: (ids: number[]) =>
    request<{ deleted: number }>("/v1/prep/memories/batch-delete", {
      method: "POST",
      body: JSON.stringify({ ids }),
    }),
};
