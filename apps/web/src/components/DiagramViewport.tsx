"use client";

/**
 * @file DiagramViewport.tsx
 * @description The scroll surface a rendered diagram lives in: measures its own
 * width, scales the diagram to fit that width and the height budget so the
 * whole chart is visible without scrolling, and layers drag-to-pan and
 * ctrl/cmd-wheel zoom on top. Owns no zoom state — it reports the factor and
 * the caller decides how to present it.
 *
 * The height budget is a CONSTANT handed in by the caller, never a measured
 * height. A measured height would track the rendered content, so a short
 * diagram would keep shrinking itself to fit its own box. The width is safe to
 * measure because the element is a block that fills its parent.
 */

import {
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";

import { ZOOM_STEP, clampZoom, fitScale, scaleSize, type DiagramSize } from "./diagramZoom";

/** Breathing room between the diagram and the viewport edge. */
const PADDING_PX = 12;

export interface DiagramViewportProps {
  /** Display-ready SVG markup. */
  svg: string;
  /** Intrinsic size from the viewBox; null when the diagram has none. */
  natural: DiagramSize | null;
  /** Multiple of the fit scale; 1 shows the whole diagram. */
  zoom: number;
  onZoomChange: (zoom: number) => void;
  /** Height budget in px the diagram is fitted into. */
  maxHeight: number;
  /** Accessible name for the rendered diagram. */
  label: string;
}

/** Whether the scroll area has anything to scroll to. */
function overflows(element: HTMLElement): boolean {
  return element.scrollWidth > element.clientWidth || element.scrollHeight > element.clientHeight;
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
  const [dragging, setDragging] = useState(false);
  const dragRef = useRef<{ x: number; y: number; left: number; top: number } | null>(null);

  // A callback ref (not useRef) so the measurement effect re-runs once the
  // node exists; useRef.current is still null on the first render.
  const attachRef = useCallback((node: HTMLDivElement | null) => {
    nodeRef.current = node;
    setElement(node);
  }, []);

  const clampedZoom = clampZoom(zoom);
  // The stage is padded on both axes and spans at least the viewport width, so
  // the padding comes out of the space the diagram may occupy on BOTH axes.
  // Leaving it out on the width side lets a width-bound chart overflow its own
  // fit by the padding and scroll at the zoom level that is supposed to fit.
  const available: DiagramSize = {
    width: Math.max(0, availableWidth - PADDING_PX * 2),
    height: maxHeight - PADDING_PX * 2,
  };
  const fit = natural ? fitScale(natural, available) : 1;
  const content = natural ? scaleSize(natural, fit * clampedZoom) : null;

  // Overflow follows from the known geometry, so it is derived rather than
  // measured: the stage is padded on both sides and spans at least the
  // viewport width, so the diagram overflows exactly when it outgrows either
  // axis. Deriving keeps the pan affordance in step with the current zoom
  // without a second DOM read that would lag one paint behind.
  const overflowing =
    content !== null && (content.width > available.width || content.height > available.height);

  // useLayoutEffect is safe here and needed for correctness: this component is
  // only mounted once a diagram has rendered, which never happens during SSR,
  // and measuring before paint avoids a flash of the un-fitted natural size.
  useLayoutEffect(() => {
    if (!element) return;
    const read = () => setAvailableWidth(Math.round(element.clientWidth));
    read();
    const observer = new ResizeObserver(read);
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);

  // ctrl/cmd + wheel zooms; a plain wheel keeps scrolling the page so a diagram
  // can never trap the scroll of a long conversation.
  useEffect(() => {
    if (!element) return;
    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      const step = event.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
      onZoomChange(clampZoom(clampedZoom * step));
    };
    element.addEventListener("wheel", onWheel, { passive: false });
    return () => element.removeEventListener("wheel", onWheel);
  }, [element, clampedZoom, onZoomChange]);

  const onPointerDown = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    const node = nodeRef.current;
    if (!node || !overflows(node)) return;
    dragRef.current = {
      x: event.clientX,
      y: event.clientY,
      left: node.scrollLeft,
      top: node.scrollTop,
    };
    node.setPointerCapture(event.pointerId);
    setDragging(true);
  }, []);

  const onPointerMove = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    const node = nodeRef.current;
    if (!drag || !node) return;
    node.scrollLeft = drag.left - (event.clientX - drag.x);
    node.scrollTop = drag.top - (event.clientY - drag.y);
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
      className={`w-full overflow-auto bg-surface-alt ${
        dragging ? "cursor-grabbing" : overflowing ? "cursor-grab" : ""
      }`}
      style={{ maxHeight }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onDoubleClick={() => onZoomChange(1)}
    >
      <div
        className={`flex items-center justify-center ${dragging ? "select-none" : ""}`}
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
              ? { width: content.width, height: content.height }
              : { width: `${clampedZoom * 100}%` }
          }
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>
    </div>
  );
});
