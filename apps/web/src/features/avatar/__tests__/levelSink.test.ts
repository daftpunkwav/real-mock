import { afterEach, describe, expect, it, vi } from "vitest";
import {
  currentTTSLevel,
  publishTTSLevel,
  resetTTSLevelSink,
  subscribeTTSLevel,
} from "../levelSink";

afterEach(() => {
  resetTTSLevelSink();
});

describe("tts level sink", () => {
  it("publishes clamped levels and serves the latest value on read", () => {
    publishTTSLevel(0.5);
    expect(currentTTSLevel()).toBe(0.5);
    publishTTSLevel(7);
    expect(currentTTSLevel()).toBe(1);
    publishTTSLevel(-1);
    expect(currentTTSLevel()).toBe(0);
  });

  it("notifies subscribers until they unsubscribe", () => {
    const seen: number[] = [];
    const unsubscribe = subscribeTTSLevel((l) => seen.push(l));
    publishTTSLevel(0.3);
    unsubscribe();
    publishTTSLevel(0.9);
    expect(seen).toEqual([0.3]);
  });

  it("a throwing listener does not break the others", () => {
    const good = vi.fn();
    subscribeTTSLevel(() => {
      throw new Error("boom");
    });
    subscribeTTSLevel(good);
    expect(() => publishTTSLevel(0.4)).not.toThrow();
    expect(good).toHaveBeenCalledWith(0.4);
  });
});
