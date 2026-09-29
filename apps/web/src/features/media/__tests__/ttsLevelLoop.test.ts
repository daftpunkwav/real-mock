import { describe, expect, it } from "vitest";
import { agcNormalize } from "../ttsLevelLoop";

describe("agcNormalize", () => {
  it("returns 0 for silence without moving the peak", () => {
    const peak = { value: 0 };
    expect(agcNormalize(0, peak)).toBe(0);
    expect(peak.value).toBe(0);
  });

  it("normalizes a quiet voice to the top of the range", () => {
    const peak = { value: 0 };
    // Sustained quiet speech: the peak adapts down to the signal.
    let level = 0;
    for (let i = 0; i < 3000; i++) level = agcNormalize(0.05, peak);
    expect(level).toBeGreaterThan(0.5);
  });

  it("keeps a loud voice from pinning the meter forever (peak decays)", () => {
    const peak = { value: 0 };
    for (let i = 0; i < 500; i++) agcNormalize(0.9, peak);
    // Signal stops: level falls back towards 0 as the peak decays.
    let level = 1;
    for (let i = 0; i < 6000; i++) level = agcNormalize(0.001, peak);
    expect(level).toBeLessThan(0.05);
  });

  it("keeps decaying the peak through silence so a quiet voice recovers", () => {
    const peak = { value: 0 };
    for (let i = 0; i < 100; i++) agcNormalize(0.9, peak);
    // ~33s of silence: the peak must decay even while rms is 0, otherwise
    // the next quiet utterance starts over-attenuated.
    for (let i = 0; i < 2000; i++) agcNormalize(0, peak);
    expect(peak.value).toBeLessThan(0.08);
    expect(agcNormalize(0.05, peak)).toBeGreaterThan(0.5);
  });
});
