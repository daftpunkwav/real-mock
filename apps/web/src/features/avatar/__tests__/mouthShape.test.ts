import { describe, expect, it } from "vitest";
import {
  MOUTH_LEVEL_FLOOR,
  advanceSyllablePhase,
  followSignal,
  mouthOpenFromLevel,
  syllableShape,
} from "../mouthShape";

describe("mouthOpenFromLevel", () => {
  it("keeps the mouth closed when silent or below the floor", () => {
    expect(mouthOpenFromLevel(0.5, false)).toBe(0);
    expect(mouthOpenFromLevel(0, true)).toBe(0);
    expect(mouthOpenFromLevel(MOUTH_LEVEL_FLOOR - 0.001, true)).toBe(0);
  });

  it("opens monotonically with level and clamps below the max", () => {
    const low = mouthOpenFromLevel(0.1, true);
    const mid = mouthOpenFromLevel(0.4, true);
    const high = mouthOpenFromLevel(0.9, true);
    expect(low).toBeGreaterThan(0);
    expect(mid).toBeGreaterThan(low);
    expect(high).toBeGreaterThan(mid);
    expect(high).toBeLessThanOrEqual(0.95);
  });
});

describe("syllableShape", () => {
  it("stays neutral at zero energy", () => {
    expect(syllableShape(0, 0)).toEqual({ wide: 0, round: 0 });
    expect(syllableShape(1.2, 0.1)).toEqual({ wide: 0, round: 0 });
  });

  it("alternates wide/round families along the phase and stays bounded", () => {
    let sawWide = false;
    let sawRound = false;
    for (let phase = 0; phase < Math.PI * 8; phase += 0.17) {
      const { wide, round } = syllableShape(phase, 0.9);
      expect(wide).toBeGreaterThanOrEqual(0);
      expect(round).toBeGreaterThanOrEqual(0);
      // The two families are mutually exclusive by construction.
      expect(wide === 0 || round === 0).toBe(true);
      if (wide > 0) sawWide = true;
      if (round > 0) sawRound = true;
    }
    expect(sawWide).toBe(true);
    expect(sawRound).toBe(true);
  });
});

describe("advanceSyllablePhase", () => {
  it("advances faster with more energy", () => {
    const quiet = advanceSyllablePhase(0, 0.1, 100);
    const loud = advanceSyllablePhase(0, 0.9, 100);
    expect(loud).toBeGreaterThan(quiet);
    expect(quiet).toBeGreaterThan(0);
  });
});

describe("followSignal", () => {
  it("attacks fast towards a higher target and releases slowly", () => {
    const up = followSignal(0, 1, 16.7);
    const down = followSignal(1, 0, 16.7);
    expect(up).toBeGreaterThan(1 - down);
  });

  it("snaps onto the target once close enough", () => {
    expect(followSignal(0.99, 1, 16.7)).toBe(1);
  });
});
