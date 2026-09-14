import { beforeEach, describe, expect, it } from "vitest";

import {
  COMPACT_INTENSITY_KEY,
  COMPACT_RETAIN_KEY,
  COMPACT_THRESHOLD_DEFAULT,
  COMPACT_THRESHOLD_KEY,
  readCompactDirective,
  readCompactIntensity,
  readCompactRetain,
  readCompactThreshold,
  resolveCompactParams,
  toCompactThresholdParam,
  writeCompactDirective,
  writeCompactIntensity,
  writeCompactRetain,
  writeCompactThreshold,
} from "../compactThreshold";

function installMemoryStorage() {
  const store = new Map<string, string>();
  (globalThis as Record<string, unknown>).window = {
    localStorage: {
      getItem: (key: string) => (store.has(key) ? (store.get(key) as string) : null),
      setItem: (key: string, value: string) => {
        store.set(key, value);
      },
    },
  };
  return store;
}

describe("compactThreshold setting", () => {
  beforeEach(() => {
    installMemoryStorage();
  });

  it("defaults to auto when nothing is stored", () => {
    expect(readCompactThreshold()).toBe("auto");
    expect(COMPACT_THRESHOLD_DEFAULT).toBe("auto");
  });

  it("round-trips the numeric thresholds", () => {
    for (const value of [0.5, 0.6, 0.7, 0.8, 0.9] as const) {
      writeCompactThreshold(value);
      expect(readCompactThreshold()).toBe(value);
    }
    writeCompactThreshold("auto");
    expect(readCompactThreshold()).toBe("auto");
  });

  it("falls back to auto on garbage", () => {
    window.localStorage.setItem(COMPACT_THRESHOLD_KEY, "0.42");
    expect(readCompactThreshold()).toBe("auto");
    window.localStorage.setItem(COMPACT_THRESHOLD_KEY, "sometimes");
    expect(readCompactThreshold()).toBe("auto");
  });

  it("maps auto to an omitted request param", () => {
    expect(toCompactThresholdParam("auto")).toBeUndefined();
    expect(toCompactThresholdParam(0.7)).toBe(0.7);
  });
});

describe("compaction preferences", () => {
  beforeEach(() => {
    installMemoryStorage();
  });

  it("round-trips intensity with a safe default", () => {
    expect(readCompactIntensity()).toBe("balanced");
    writeCompactIntensity("aggressive");
    expect(readCompactIntensity()).toBe("aggressive");
    window.localStorage.setItem(COMPACT_INTENSITY_KEY, "turbo");
    expect(readCompactIntensity()).toBe("balanced");
  });

  it("trims and bounds the directive", () => {
    expect(readCompactDirective()).toBe("");
    writeCompactDirective("  prioritize errors  ");
    expect(readCompactDirective()).toBe("prioritize errors");
    writeCompactDirective("x".repeat(600));
    expect(readCompactDirective()).toHaveLength(500);
  });

  it("rejects negative and non-integer retain values", () => {
    expect(readCompactRetain()).toBe(4);
    writeCompactRetain(10);
    expect(readCompactRetain()).toBe(10);
    writeCompactRetain(0);
    expect(readCompactRetain()).toBe(0);
    window.localStorage.setItem(COMPACT_RETAIN_KEY, "-3");
    expect(readCompactRetain()).toBe(4);
    window.localStorage.setItem(COMPACT_RETAIN_KEY, "2.5");
    expect(readCompactRetain()).toBe(4);
    window.localStorage.setItem(COMPACT_RETAIN_KEY, "9999");
    expect(readCompactRetain()).toBe(200);
  });

  it("resolves the full per-turn params", () => {
    writeCompactIntensity("light");
    writeCompactDirective("focus on decisions");
    writeCompactRetain(6);
    expect(resolveCompactParams()).toEqual({
      intensity: "light",
      directive: "focus on decisions",
      retain: 6,
    });
  });
});
