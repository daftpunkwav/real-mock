"use client";

/**
 * @file usePreviewViewport.ts
 * @description Pan / zoom / current-page tracking for the original-file preview.
 *
 * Zoom bounds live in resumeLimits. Must not fetch files.
 */

import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import {
  clampPreviewZoom,
  PREVIEW_MAX_ZOOM,
  PREVIEW_MIN_ZOOM,
  PREVIEW_ZOOM_STEP,
} from "../../resumeLimits";

export const MIN_ZOOM = PREVIEW_MIN_ZOOM;
export const MAX_ZOOM = PREVIEW_MAX_ZOOM;
export const ZOOM_STEP = PREVIEW_ZOOM_STEP;

export function clampZoom(z: number): number {
  return clampPreviewZoom(z);
}

/** Pan, zoom, and current-page tracking for file preview. */
export function usePreviewViewport() {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<(HTMLImageElement | null)[]>([]);
  const scrollTicking = useRef(false);
  const dragRef = useRef<{ x: number; y: number; sl: number; st: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [baseWidth, setBaseWidth] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);

  // Throttle page tracking to one rAF per scroll burst.
  const onScroll = useCallback(() => {
    if (scrollTicking.current) return;
    scrollTicking.current = true;
    requestAnimationFrame(() => {
      scrollTicking.current = false;
      const el = scrollerRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      let cur = 1;
      pageRefs.current.forEach((img, idx) => {
        if (img && img.getBoundingClientRect().top - rect.top <= rect.height * 0.5) {
          cur = idx + 1;
        }
      });
      setCurrentPage(cur);
    });
  }, []);

  // Track container width for preview sizing.
  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const update = () => setBaseWidth(Math.max(320, el.clientWidth - 32));
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const zoomAt = useCallback((factor: number, anchorX: number, anchorY: number) => {
    const el = scrollerRef.current;
    if (!el) return;
    setZoom((prev) => {
      const next = clampZoom(prev * factor);
      if (next === prev) return prev;
      const ratio = next / prev;
      // Keep the zoom anchor stable across scale changes.
      requestAnimationFrame(() => {
        el.scrollLeft = (el.scrollLeft + anchorX) * ratio - anchorX;
        el.scrollTop = (el.scrollTop + anchorY) * ratio - anchorY;
      });
      return next;
    });
  }, []);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      zoomAt(e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP, e.clientX - rect.left, e.clientY - rect.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomAt]);

  const onPointerDown = (e: ReactPointerEvent) => {
    // Left-button mouse drag only.
    if (e.pointerType !== "mouse" || e.button !== 0) return;
    const el = scrollerRef.current;
    if (!el) return;
    dragRef.current = { x: e.clientX, y: e.clientY, sl: el.scrollLeft, st: el.scrollTop };
    setDragging(true);
  };

  const onPointerMove = (e: ReactPointerEvent) => {
    const drag = dragRef.current;
    const el = scrollerRef.current;
    if (!drag || !el) return;
    el.scrollLeft = drag.sl - (e.clientX - drag.x);
    el.scrollTop = drag.st - (e.clientY - drag.y);
  };

  const endDrag = () => {
    dragRef.current = null;
    setDragging(false);
  };

  const panProps = {
    onPointerDown,
    onPointerMove,
    onPointerUp: endDrag,
    onPointerLeave: endDrag,
  };

  return { scrollerRef, pageRefs, zoom, baseWidth, currentPage, dragging, zoomAt, setZoom, onScroll, panProps };
}
