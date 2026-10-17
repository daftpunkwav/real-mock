/** Diagram viewport sizing: fit a chart into a box, and step the zoom factor. */

import { describe, expect, it } from "vitest";

import {
  ZOOM_MAX,
  ZOOM_MIN,
  clampZoom,
  fitScale,
  isUsableSize,
  scaleSize,
  zoomIn,
  zoomOut,
} from "../diagramZoom";

describe("isUsableSize", () => {
  it("rejects any zero or negative dimension", () => {
    expect(isUsableSize({ width: 10, height: 10 })).toBe(true);
    expect(isUsableSize({ width: 0, height: 10 })).toBe(false);
    expect(isUsableSize({ width: 10, height: 0 })).toBe(false);
  });
});

describe("fitScale", () => {
  it("shrinks a diagram so both dimensions fit the box", () => {
    // 1000x1000 in a 400x200 box is limited by the height.
    expect(fitScale({ width: 1000, height: 1000 }, { width: 400, height: 200 })).toBe(0.2);
  });

  it("shrinks to the width when width is the binding constraint", () => {
    expect(fitScale({ width: 1000, height: 100 }, { width: 400, height: 900 })).toBe(0.4);
  });

  it("never enlarges a diagram smaller than its box", () => {
    expect(fitScale({ width: 100, height: 50 }, { width: 800, height: 600 })).toBe(1);
  });

  it("shows the whole diagram exactly when it is the binding fit", () => {
    const natural = { width: 640, height: 480 };
    expect(fitScale(natural, { width: 320, height: 240 })).toBe(0.5);
    expect(scaleSize(natural, 0.5)).toEqual({ width: 320, height: 240 });
  });

  it("falls back to the natural size for an unmeasured or degenerate box", () => {
    // Zero is what the viewport reports before its first measurement.
    expect(fitScale({ width: 1000, height: 1000 }, { width: 0, height: 0 })).toBe(1);
    expect(fitScale({ width: 0, height: 0 }, { width: 800, height: 600 })).toBe(1);
  });
});

describe("scaleSize", () => {
  it("never collapses a dimension to zero", () => {
    expect(scaleSize({ width: 4, height: 4 }, 0.01)).toEqual({ width: 1, height: 1 });
  });
});

describe("zoom factor", () => {
  it("keeps the factor inside the supported range", () => {
    expect(clampZoom(0.01)).toBe(ZOOM_MIN);
    expect(clampZoom(999)).toBe(ZOOM_MAX);
    expect(clampZoom(Number.NaN)).toBe(1);
    expect(clampZoom(1.5)).toBe(1.5);
  });

  it("steps up and down without leaving the range", () => {
    expect(zoomIn(1)).toBeGreaterThan(1);
    expect(zoomOut(zoomIn(2))).toBeCloseTo(2, 5);
    expect(zoomOut(ZOOM_MIN)).toBe(ZOOM_MIN);
    expect(zoomIn(ZOOM_MAX)).toBe(ZOOM_MAX);
  });
});
