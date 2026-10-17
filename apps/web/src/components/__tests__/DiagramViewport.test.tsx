// @vitest-environment jsdom
/**
 * DiagramViewport wiring: the diagram is sized to fit the measured box, and
 * zoom is reported rather than owned. jsdom has no layout engine, so the
 * container's width is stubbed — that is the one input the fit depends on.
 */

import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { DiagramViewport } from "../DiagramViewport";
import { ZOOM_MAX, ZOOM_MIN } from "../diagramZoom";

const VIEWPORT_WIDTH_PX = 400;
const MAX_HEIGHT_PX = 480;

const SVG = '<svg viewBox="0 0 400 800"><g/></svg>';

interface RenderOptions {
  natural: { width: number; height: number } | null;
  zoom?: number;
  onZoomChange?: (zoom: number) => void;
}

function renderDiagram({ natural, zoom = 1, onZoomChange = vi.fn() }: RenderOptions) {
  const result = render(
    <DiagramViewport
      svg={SVG}
      natural={natural}
      zoom={zoom}
      onZoomChange={onZoomChange}
      maxHeight={MAX_HEIGHT_PX}
      label="test diagram"
    />,
  );
  return {
    ...result,
    diagram: result.container.querySelector<HTMLElement>("[role='img']")!,
    onZoomChange,
  };
}

function renderViewport(zoom = 1, onZoomChange: (value: number) => void = vi.fn()) {
  return renderDiagram({ natural: { width: 400, height: 800 }, zoom, onZoomChange });
}

beforeAll(() => {
  // jsdom reports 0 for every box; the fit needs a real width to divide by.
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get: () => VIEWPORT_WIDTH_PX,
  });
  // jsdom ships no ResizeObserver; the stub only has to be inert, since the
  // viewport reads the measurement once on mount.
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
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
    const { diagram } = renderDiagram({ natural: null });
    expect(diagram.style.width).toBe("100%");
    expect(diagram.style.height).toBe("");
  });

  it("zooms on ctrl+wheel and leaves a plain wheel to the page", () => {
    const onZoomChange = vi.fn<(value: number) => void>();
    const { container } = renderViewport(1, onZoomChange);
    const viewport = container.firstElementChild as HTMLElement;

    fireEvent.wheel(viewport, { deltaY: -100, ctrlKey: true });
    expect(onZoomChange).toHaveBeenCalledTimes(1);
    expect(onZoomChange.mock.calls[0]?.[0]).toBeGreaterThan(1);

    fireEvent.wheel(viewport, { deltaY: 100 });
    expect(onZoomChange).toHaveBeenCalledTimes(1);
  });

  it("resets to fit on double click", () => {
    const { container, onZoomChange } = renderViewport(3);
    fireEvent.doubleClick(container.firstElementChild as HTMLElement);
    expect(onZoomChange).toHaveBeenCalledWith(1);
  });
});
