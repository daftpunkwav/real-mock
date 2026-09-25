// @vitest-environment jsdom
/**
 * @file useGrowthPage.test.tsx
 * @description Tests for the AI-insight slice of useGrowthPage: degraded
 * payload normalization and the regen polling state machine.
 */

import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { normalizeInsight, useGrowthPage } from "../useGrowthPage";
import { growthHttp as api } from "@/lib/api/clients";
import type { GrowthInsight } from "@/lib/api/clients";

vi.mock("@/lib/api/clients", () => ({
  growthHttp: {
    getGrowthHistory: vi.fn(),
    getSystemInsights: vi.fn(),
    getAggregated: vi.fn(),
    getInsight: vi.fn(),
    refreshInsight: vi.fn(),
  },
}));

const mockedGetInsight = vi.mocked(api.getInsight);
const mockedRefreshInsight = vi.mocked(api.refreshInsight);

function makeInsight(headline: string): GrowthInsight {
  return {
    headline,
    trajectory: "trajectory",
    trajectory_stage: "rising",
    recurring_weaknesses: [],
    improving_areas: [],
    resume_gap_insights: [],
    training_plan: [],
    generated_at: null,
    session_count: 2,
    locale: "zh-CN",
  };
}

const OLD_INSIGHT = makeInsight("old");
const NEW_INSIGHT = makeInsight("new");

function mockStableLoads() {
  vi.mocked(api.getGrowthHistory).mockResolvedValue([]);
  vi.mocked(api.getSystemInsights).mockRejectedValue(new Error("down"));
  vi.mocked(api.getAggregated).mockRejectedValue(new Error("down"));
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("normalizeInsight", () => {
  it("fills missing array fields from a degraded payload", () => {
    // The store falls back to an empty object for corrupted JSON, which the
    // backend then serves as an insight with no arrays at all.
    const degraded = { headline: "h", trajectory: "t" } as unknown as GrowthInsight;
    const out = normalizeInsight(degraded);
    expect(out.recurring_weaknesses).toEqual([]);
    expect(out.improving_areas).toEqual([]);
    expect(out.resume_gap_insights).toEqual([]);
    expect(out.training_plan).toEqual([]);
  });

  it("fills missing per-focus actions without dropping the focus", () => {
    const degraded = {
      ...makeInsight("h"),
      training_plan: [{ area: "sql", based_on: "sid 1" }],
    } as unknown as GrowthInsight;
    const out = normalizeInsight(degraded);
    expect(out.training_plan).toEqual([{ area: "sql", based_on: "sid 1", actions: [] }]);
  });

  it("keeps a well-formed payload intact", () => {
    const full = {
      ...makeInsight("h"),
      recurring_weaknesses: [{ skill: "sql", count: 2, trend: "stable", advice: "drill" }],
      training_plan: [{ area: "sql", based_on: "sid 1", actions: ["drill"] }],
    };
    expect(normalizeInsight(full)).toEqual(full);
  });
});

describe("useGrowthPage insight polling", () => {
  it("keeps polling while a regen runs and applies the fresh insight when it settles", async () => {
    vi.useFakeTimers();
    try {
      mockStableLoads();
      mockedGetInsight.mockResolvedValue({ insight: OLD_INSIGHT, status: "ready" });
      const { result } = renderHook(() => useGrowthPage());
      await act(async () => {});
      expect(result.current.aiStatus).toBe("ready");
      expect(result.current.aiInsight?.headline).toBe("old");

      mockedRefreshInsight.mockResolvedValue({ scheduled: true, status: "generating" });
      await act(async () => {
        await result.current.refreshInsight();
      });
      expect(result.current.aiStatus).toBe("generating");

      // Poll tick while still regenerating: must not settle on the stale
      // snapshot just because one exists.
      mockedGetInsight.mockResolvedValue({ insight: OLD_INSIGHT, status: "generating" });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });
      expect(result.current.aiStatus).toBe("generating");

      // Regen finished: the fresh analysis replaces the stale one.
      mockedGetInsight.mockResolvedValue({ insight: NEW_INSIGHT, status: "ready" });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });
      expect(result.current.aiStatus).toBe("ready");
      expect(result.current.aiInsight?.headline).toBe("new");
    } finally {
      vi.useRealTimers();
    }
  });

  it("stays generating on first load while a regen is in flight, then settles", async () => {
    vi.useFakeTimers();
    try {
      mockStableLoads();
      mockedGetInsight.mockResolvedValue({ insight: OLD_INSIGHT, status: "generating" });
      const { result } = renderHook(() => useGrowthPage());
      await act(async () => {});
      expect(result.current.aiStatus).toBe("generating");

      mockedGetInsight.mockResolvedValue({ insight: OLD_INSIGHT, status: "ready" });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });
      expect(result.current.aiStatus).toBe("ready");
    } finally {
      vi.useRealTimers();
    }
  });
});
