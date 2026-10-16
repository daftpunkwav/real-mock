/**
 * @file diagramZoom.ts
 * @description Pure sizing math for the diagram viewport: fit a diagram's
 * intrinsic (viewBox) size into an available box, and step a zoom factor
 * without leaving the supported range. Framework-free and side-effect free so
 * the viewport component stays declarative and the math is unit-testable.
 *
 * Zoom is expressed as a MULTIPLE OF THE FIT SCALE rather than as a percentage
 * of the natural size: 1 means "the whole diagram is visible", which is the
 * only anchor that stays correct across container sizes and across the
 * fullscreen viewer opening at a different size.
 *
 * Constraints:
 * - This module must not touch the DOM, measure anything, or hold state; the
 *   caller supplies the measured box.
 */

/** Diagram sizes are in CSS pixels; both dimensions must be positive. */
export interface DiagramSize {
  width: number;
  height: number;
}

/** Zoom below this is unreadable noise; above it the SVG is just blurry space. */
export const ZOOM_MIN = 0.25;
export const ZOOM_MAX = 8;

/** One press of zoom in / zoom out multiplies by this factor. */
export const ZOOM_STEP = 1.25;

/** True for a usable size; guards every division against a zero-sized box. */
export function isUsableSize(size: DiagramSize): boolean {
  return size.width > 0 && size.height > 0;
}

export function clampZoom(zoom: number): number {
  if (!Number.isFinite(zoom)) return 1;
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, zoom));
}

export function zoomIn(zoom: number): number {
  return clampZoom(zoom * ZOOM_STEP);
}

export function zoomOut(zoom: number): number {
  return clampZoom(zoom / ZOOM_STEP);
}

/**
 * Largest scale at which the whole diagram fits inside `box`.
 *
 * Capped at 1 so a diagram smaller than its container keeps its natural size
 * instead of being blown up into unreadable, blurry shapes.
 */
export function fitScale(natural: DiagramSize, box: DiagramSize): number {
  if (!isUsableSize(natural) || !isUsableSize(box)) return 1;
  return Math.min(1, box.width / natural.width, box.height / natural.height);
}

/** The pixel box the diagram occupies once scaled; never smaller than 1px. */
export function scaleSize(natural: DiagramSize, scale: number): DiagramSize {
  return {
    width: Math.max(1, Math.round(natural.width * scale)),
    height: Math.max(1, Math.round(natural.height * scale)),
  };
}
