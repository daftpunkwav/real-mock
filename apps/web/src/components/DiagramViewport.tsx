"use client";

/**
 * @file DiagramViewport.tsx
 * @description The surface a rendered diagram lives in: measures its own width,
 * scales the diagram to fit that width and the height budget so the whole chart
 * is visible without scrolling, and layers drag-to-pan and ctrl/cmd-wheel zoom
 * on top. Owns no zoom state — it reports the factor and the caller decides how
 * to present it.
 *
 * Two layout decisions are load-bearing:
 *
 * The height budget is a CONSTANT handed in by the caller, never a measured
 * height. A measured height would track the rendered content, so a short
 * diagram would keep shrinking itself to fit its own box.
 *
 * The vertical axis is deliberately NOT a scroll container (overflow-y is
 * clip). The block grows with the diagram instead, which keeps the fit's
 * "whole chart visible" promise without a nested scrollbar and lets a plain
 * wheel over a diagram scroll the conversation rather than the chart. The
 * horizontal axis stays scrollable because a zoomed diagram is wider than the
 * column. Any fullscreen scroll container belongs to the modal around this,
 * where trapping the scroll is correct because the page behind is locked.
 */

import {
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type Dispatch,
  type PointerEvent as ReactPointerEvent,
  type SetStateAction,
} from "react";

import { ZOOM_STEP, clampZoom, fitScale, scaleSize, type DiagramSize } from "./diagramZoom";

/** Breathing room between the diagram and the stage edge. */
const PADDING_PX = 12;

export interface DiagramViewportProps {
  /** Display-ready SVG markup. */
  svg: string;
  /** Intrinsic size from the viewBox; null when the diagram has none. */
  natural: DiagramSize | null;
  /** Multiple of the fit scale; 1 shows the whole diagram. */
  zoom: number;
  /**
   * Accepts an updater so burst input — several wheel events inside a single
   * React commit — steps from the latest zoom rather than the last rendered
   * one.
   */
  onZoomChange: Dispatch<SetStateAction<number>>;
  /**
   * Height budget in px, or "parent" to measure the element's own parent.
   *
   * A number is used directly because a measured height would track the
   * rendered content and a short diagram would shrink itself forever. "parent"
   * is for a stage whose height the surrounding layout already fixes — the
   * fullscreen modal — where measuring the element itself would be circular.
   */
  maxHeight: number | "parent";
  /** Accessible name for the rendered diagram. */
  label: string;
}

/** Whether the stage has anything to pan horizontally. */
function overflowsX(element: HTMLElement): boolean {
  return element.scrollWidth > element.clientWidth;
}

export const DiagramViewport = memo(function DiagramViewport({
  svg,
  natural,
  zoom,
  onZoomChange,
  maxHeight,
  label,
}: DiagramViewportProps) {
  const nodeRef = useRef<HTMLDivElement | null>(null);
  const [element, setElement] = useState<HTMLDivElement | null>(null);
  const [availableWidth, setAvailableWidth] = useState(0);
  const [parentHeight, setParentHeight] = useState(0);
  const [dragging, setDragging] = useState(false);
  const dragRef = useRef<{ x: number; y: number; left: number } | null>(null);

  // A callback ref (not useRef) so the measurement effect re-runs once the node
  // exists; useRef.current is still null on the first render.
  const attachRef = useCallback((node: HTMLDivElement | null) => {
    nodeRef.current = node;
    setElement(node);
  }, []);

  const clampedZoom = clampZoom(zoom);
  // The stage is padded on both axes and spans at least the viewport width, so
  // the padding comes out of the space the diagram may occupy on BOTH axes.
  // Leaving it out on the width side lets a width-bound chart overflow its own
  // fit by the padding and scroll at the zoom level that is supposed to fit.
  const budgetHeight = maxHeight === "parent" ? parentHeight : maxHeight;
  const available: DiagramSize = {
    width: Math.max(0, availableWidth - PADDING_PX * 2),
    height: budgetHeight - PADDING_PX * 2,
  };
  const fit = natural ? fitScale(natural, available) : 1;
  const content = natural ? scaleSize(natural, fit * clampedZoom) : null;

  // Horizontal overflow follows from the known geometry, so it is derived rather
  // than measured: the stage is padded and spans at least the viewport width,
  // so the diagram outgrows it exactly when it is wider than the usable box.
  // Deriving keeps the pan affordance in step with the current zoom without a
  // DOM read that would lag one paint behind.
  const overflowing = content !== null && content.width > available.width;

  // useLayoutEffect is safe here and needed for correctness: this component is
  // only mounted once a diagram has rendered, which never happens during SSR,
  // and measuring before paint avoids a flash of the un-fitted natural size.
  // The parent is observed too because a vertical window resize changes its
  // height without changing this element's width.
  useLayoutEffect(() => {
    if (!element) return;
    const parent = maxHeight === "parent" ? element.parentElement : null;
    const read = () => {
      setAvailableWidth(Math.round(element.clientWidth));
      if (parent) setParentHeight(Math.round(parent.clientHeight));
    };
    read();
    const observer = new ResizeObserver(read);
    observer.observe(element);
    if (parent) observer.observe(parent);
    return () => observer.disconnect();
  }, [element, maxHeight]);

  // ctrl/cmd + wheel zooms, stepped through an updater so a burst of events
  // within one React commit still registers every step. A plain wheel is left
  // entirely alone: the vertical axis is not a scroll container, so it reaches
  // the conversation, and a horizontal wheel pans the zoomed chart natively.
  useEffect(() => {
    if (!element) return;
    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      const step = event.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
      onZoomChange((current) => clampZoom(clampZoom(current) * step));
    };
    element.addEventListener("wheel", onWheel, { passive: false });
    return () => element.removeEventListener("wheel", onWheel);
  }, [element, onZoomChange]);

  const onPointerDown = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    const node = nodeRef.current;
    if (!node || !overflowsX(node)) return;
    dragRef.current = { x: event.clientX, y: event.clientY, left: node.scrollLeft };
    node.setPointerCapture(event.pointerId);
    setDragging(true);
  }, []);

  const onPointerMove = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    const node = nodeRef.current;
    if (!drag || !node) return;
    node.scrollLeft = drag.left - (event.clientX - drag.x);
  }, []);

  const endDrag = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (!dragRef.current) return;
    dragRef.current = null;
    setDragging(false);
    nodeRef.current?.releasePointerCapture(event.pointerId);
  }, []);

  return (
    <div
      ref={attachRef}
      className={`w-full bg-surface-alt ${dragging ? "cursor-grabbing" : overflowing ? "cursor-grab" : ""}`}
      // overflow-y stays clip so the block grows with the diagram and a plain
      // wheel reaches the page; only the horizontal axis pans.
      style={{ overflowX: "auto", overflowY: "clip" }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onDoubleClick={() => onZoomChange(1)}
    >
      <div
        className={`flex items-center ${dragging ? "select-none" : ""}`}
        style={{ minWidth: "100%", padding: PADDING_PX }}
      >
        {/*
          The one HTML sink in the app, and it is deliberate: a mermaid chart is
          only ever available as a markup string, and the chart itself is
          LLM-authored. The trust boundary is closed upstream, not here:
          renderDiagramSvg runs mermaid under securityLevel "strict" (labels
          through DOMPurify, no click handlers, no navigation) and then passes
          the output through sanitizeDiagramSvg, which strips script,
          foreignObject, embed, object, iframe, link and meta elements, inline
          event handlers and javascript:/data:text/html URLs. Only that
          sanitized string ever reaches this prop, and it lands in a
          role="img" container that offers no navigation target. diagramRender
          test.ts asserts the sanitizer and the label path together.
        */}
        <div
          role="img"
          aria-label={label}
          className="shrink-0"
          style={
            content
              ? // Centering an oversized box puts its left edge before the
                // scroll origin, where scrollLeft can never reach. Auto margins
                // centre it while it fits and collapse to zero once it does not.
                { width: content.width, height: content.height, margin: "0 auto" }
              : { width: "100%" }
          }
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>
    </div>
  );
});
