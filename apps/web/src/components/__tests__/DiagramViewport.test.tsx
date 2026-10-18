// @vitest-environment jsdom
/**
 * DiagramViewport wiring: the diagram is sized to fit the measured box, and
 * zoom is reported rather than owned. jsdom has no layout engine, so the
 * container's width is stubbed — that is the one input the fit depends on.
 */

import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { Dispatch, SetStateAction } from "react";

import { DiagramViewport } from "../DiagramViewport";
import { ZOOM_MAX, ZOOM_MIN } from "../diagramZoom";

const VIEWPORT_WIDTH_PX = 400;
const MAX_HEIGHT_PX = 480;

const SVG = '<svg viewBox="0 0 400 800"><g/></svg>';

/** Callbacks handed to the stub observer, so a test can drive a measurement. */
let observerCallbacks: (() => void)[] = [];

function fireResizeObservers(): void {
  act(() => {
    observerCallbacks.forEach((callback) => callback());
  });
}

interface RenderOptions {
  natural: { width: number; height: number } | null;
  zoom?: number;
  maxHeight?: number | "parent";
  onZoomChange?: Dispatch<SetStateAction<number>>;
}

function renderDiagram({
  natural,
  zoom = 1,
  maxHeight = MAX_HEIGHT_PX,
  onZoomChange = vi.fn(),
}: RenderOptions) {
  observerCallbacks = [];
  const result = render(
    <DiagramViewport
      svg={SVG}
      natural={natural}
      zoom={zoom}
      onZoomChange={onZoomChange}
      maxHeight={maxHeight}
      label="test diagram"
    />,
  );
  return {
    ...result,
    diagram: result.container.querySelector<HTMLElement>("[role='img']")!,
    onZoomChange,
  };
}

function renderViewport(zoom = 1, onZoomChange: Dispatch<SetStateAction<number>> = vi.fn()) {
  return renderDiagram({ natural: { width: 400, height: 800 }, zoom, onZoomChange });
}

beforeAll(() => {
  // jsdom reports 0 for every box; the fit needs a real width to divide by.
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get: () => VIEWPORT_WIDTH_PX,
  });
  // jsdom has no ResizeObserver; the stub records its callback so a test can
  // drive a measurement, and does nothing else. The pointer-capture calls are
  // bookkeeping the browser keeps for us, so no-ops suffice.
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(callback: () => void) {
        observerCallbacks.push(callback);
      }
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  HTMLElement.prototype.setPointerCapture ??= () => {};
  HTMLElement.prototype.releasePointerCapture ??= () => {};
});

afterEach(cleanup);

describe("DiagramViewport", () => {
  it("scales the diagram down so the whole chart fits the height budget", () => {
    // 400x800 into 376 x (480 - 2 * 12) is limited by the height: 456 / 800.
    const { diagram } = renderViewport();
    expect(diagram.style.width).toBe("228px");
    expect(diagram.style.height).toBe("456px");
  });

  it("keeps the stage padding out of the width the diagram may use", () => {
    // Wide and short, so the width binds: 376 / 600 rather than 400 / 600.
    const { diagram } = renderDiagram({ natural: { width: 600, height: 200 } });
    expect(diagram.style.width).toBe(`${VIEWPORT_WIDTH_PX - 24}px`);
    expect(diagram.style.height).toBe(`${Math.round((VIEWPORT_WIDTH_PX - 24) * (200 / 600))}px`);
  });

  it("multiplies the fit by the zoom factor", () => {
    const { diagram } = renderViewport(2);
    expect(diagram.style.width).toBe("456px");
    expect(diagram.style.height).toBe("912px");
  });

  it("clamps the zoom factor it applies", () => {
    // Fit height is 456px, so a clamped factor multiplies exactly that.
    expect(renderViewport(ZOOM_MAX + 10).diagram.style.height).toBe(`${456 * ZOOM_MAX}px`);
    expect(renderViewport(ZOOM_MIN / 2).diagram.style.height).toBe(`${456 * ZOOM_MIN}px`);
  });

  it("falls back to a fluid width when the diagram has no viewBox", () => {
    // Defensive only: fitDiagramSvg now synthesizes a viewBox from a stated
    // pixel size, so a mermaid root always reaches the wrapper with one.
    const { diagram } = renderDiagram({ natural: null });
    expect(diagram.style.width).toBe("100%");
    expect(diagram.style.height).toBe("");
  });

  it("zooms on ctrl+wheel and prevents the browser default", () => {
    const onZoomChange = vi.fn<Dispatch<SetStateAction<number>>>();
    const { container } = renderViewport(1, onZoomChange);
    const viewport = container.firstElementChild as HTMLElement;

    const zoomed = new WheelEvent("wheel", { deltaY: -100, ctrlKey: true, cancelable: true });
    viewport.dispatchEvent(zoomed);
    expect(onZoomChange).toHaveBeenCalledTimes(1);
    expect(zoomed.defaultPrevented).toBe(true);

    // The step arrives as an updater, so a burst of events inside one React
    // commit keeps stepping instead of collapsing onto the same value.
    const updater = onZoomChange.mock.calls[0]?.[0];
    expect(typeof updater).toBe("function");
    expect((updater as (value: number) => number)(1)).toBeGreaterThan(1);
    expect((updater as (value: number) => number)(2)).toBeGreaterThan(
      (updater as (value: number) => number)(1),
    );
  });

  it("never traps a plain wheel: no zoom and no default prevented", () => {
    const onZoomChange = vi.fn<Dispatch<SetStateAction<number>>>();
    const { container } = renderViewport(1, onZoomChange);
    const viewport = container.firstElementChild as HTMLElement;

    // Checking the call count alone would pass even if the handler swallowed
    // the event, which is what trapping the page scroll actually looks like.
    const plain = new WheelEvent("wheel", { deltaY: 120, cancelable: true });
    viewport.dispatchEvent(plain);
    expect(onZoomChange).not.toHaveBeenCalled();
    expect(plain.defaultPrevented).toBe(false);
  });

  it("keeps the vertical axis out of the scroll chain", () => {
    const { container } = renderViewport(1);
    const viewport = container.firstElementChild as HTMLElement;
    // A vertical scroll container here would eat a plain wheel before the
    // conversation ever sees it.
    expect(viewport.style.overflowY).toBe("clip");
    expect(viewport.style.overflowX).toBe("auto");
  });

  it("anchors an oversized diagram to the scroll origin", () => {
    const { diagram } = renderViewport(4);
    // Fit is 456/800, so 4x lands at 912x1824 — wider than the usable box.
    expect(diagram.style.width).toBe("912px");
    expect(diagram.style.height).toBe("1824px");
    // justify-content:center would place the left edge before scrollLeft's
    // origin; auto margins collapse to zero instead.
    expect(diagram.style.margin).toBe("0px auto");
  });

  it("fits into the parent stage when the budget is 'parent'", () => {
    // A stage whose height the surrounding layout fixes: the viewport has to
    // measure it, because no number can be derived without the DOM.
    const { diagram } = renderDiagram({
      natural: { width: 400, height: 800 },
      maxHeight: "parent",
    });
    // The measured parent is the element wrapping the viewport root.
    const stage = diagram.parentElement?.parentElement?.parentElement;
    expect(stage).toBeTruthy();
    Object.defineProperty(stage!, "clientHeight", { configurable: true, value: 300 });

    act(() => fireResizeObservers());
    expect(diagram.style.height).toBe(`${300 - 24}px`);
  });

  it("pans horizontally while a pointer drag is held", () => {
    const { container } = renderViewport(4);
    const viewport = container.firstElementChild as HTMLElement;
    // jsdom reports every box as zero, so the pan precondition needs a real
    // overflow to report.
    Object.defineProperty(viewport, "scrollWidth", { configurable: true, value: 2000 });
    Object.defineProperty(viewport, "clientWidth", { configurable: true, value: 758 });
    viewport.scrollLeft = 300;

    fireEvent.pointerDown(viewport, { button: 0, clientX: 500, clientY: 200, pointerId: 1 });
    fireEvent.pointerMove(viewport, { clientX: 460, clientY: 200, pointerId: 1 });
    // Dragging left by 40px pulls the content right by the same amount.
    expect(viewport.scrollLeft).toBe(340);
  });

  it("resets to fit on double click", () => {
    const { container, onZoomChange } = renderViewport(3);
    fireEvent.doubleClick(container.firstElementChild as HTMLElement);
    expect(onZoomChange).toHaveBeenCalledWith(1);
  });
});
