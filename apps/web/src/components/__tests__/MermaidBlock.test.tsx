// @vitest-environment jsdom
/**
 * @file MermaidBlock.test.tsx
 * @description The dual view stays honest before a diagram exists: selecting
 * Source must show the chart source, which is the only thing left to show
 * while a chart is still rendering or has failed outright.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/LocaleProvider";
import { MermaidBlock } from "../MermaidBlock";

const CHART = 'flowchart TB\n  A["one"] --> B["two"]';

/**
 * Budget for the engine's cold start, outside every test's own timeout.
 *
 * The first real render pays mermaid's lazy ESM load: ~19 MB of engine chunks
 * across ~280 modules. That takes seconds on an idle machine and tens of
 * seconds while the whole suite runs in parallel (one isolated worker per test
 * file), so the load is hoisted into beforeAll: the tests below then only
 * budget their own render passes instead of failing on the engine's startup.
 */
const COLD_ENGINE_LOAD_TIMEOUT_MS = 120_000;

/**
 * Budget for one real diagram render in this file. Rendering waits on the
 * engine's layout pass; it is normally sub-second once loaded, but the suite
 * runs every test file in its own worker, so a loaded machine stretches it.
 */
const RENDER_WAIT_TIMEOUT_MS = 60_000;

/** Test budget covering one render wait plus the interactions around it. */
const RENDER_TEST_TIMEOUT_MS = 70_000;

beforeAll(async () => {
  // jsdom ships no ResizeObserver; the viewport mounts inside this component.
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  HTMLElement.prototype.setPointerCapture ??= () => {};
  HTMLElement.prototype.releasePointerCapture ??= () => {};

  // mermaid measures text through SVG layout APIs jsdom does not implement, so
  // a chart can never render here without standing in for the browser's text
  // metrics. The numbers are irrelevant; only that layout can run.
  const prototype = window.SVGElement.prototype as unknown as Record<string, unknown>;
  prototype.getBBox = function getBBox(this: SVGElement) {
    const text = this.textContent ?? "";
    return { x: 0, y: 0, width: text.length * 8, height: 20 };
  };
  prototype.getComputedTextLength = function getComputedTextLength(this: SVGElement) {
    return (this.textContent ?? "").length * 8;
  };
  // Identical specifier as renderDiagramSvg's lazy import, so this is the same
  // module the component's render passes below reuse.
  await import("mermaid");
}, COLD_ENGINE_LOAD_TIMEOUT_MS);

afterEach(cleanup);

function renderBlock() {
  return render(
    <LocaleProvider>
      <MermaidBlock chart={CHART} />
    </LocaleProvider>,
  );
}

/** The Source tab, by its accessible name. */
function sourceTab(): HTMLElement {
  return screen.getByRole("tab", { name: /source|源码/i });
}

/** Text of the rendered source block, or null when no source pane is shown. */
function renderedSource(container: HTMLElement): string | null {
  return container.querySelector("code")?.textContent ?? null;
}

/**
 * Open the fullscreen viewer and return its backdrop and panel.
 *
 * The viewer is only reachable once a diagram exists, so this waits for the
 * real render rather than stubbing it out.
 */
async function openFullscreen() {
  const result = renderBlock();
  const fullscreenButton = () => screen.getByRole("button", { name: /fullscreen|全屏/i });
  // The viewer is disabled until a diagram exists, so wait for the real render
  // rather than clicking a disabled control.
  await waitFor(
    () => {
      if ((fullscreenButton() as HTMLButtonElement).disabled) {
        throw new Error("fullscreen control is still disabled");
      }
    },
    { timeout: RENDER_WAIT_TIMEOUT_MS },
  );
  fireEvent.click(fullscreenButton());
  const backdrop = result.container.querySelector('[role="dialog"]');
  if (!backdrop) throw new Error("fullscreen viewer did not open");
  return { ...result, backdrop, panel: backdrop.firstElementChild as HTMLElement };
}

describe("MermaidBlock", () => {
  it("shows the source when Source is picked before a diagram exists", () => {
    // Still inside the render debounce, so no svg has been produced yet — the
    // state the Source tab exists for.
    const { container } = renderBlock();
    fireEvent.click(sourceTab());
    expect(renderedSource(container)).toBe(CHART);
  });

  it("keeps showing the source after switching back and forth without a diagram", () => {
    const { container } = renderBlock();
    fireEvent.click(sourceTab());
    fireEvent.click(screen.getByRole("tab", { name: /diagram|图表/i }));
    fireEvent.click(sourceTab());
    expect(renderedSource(container)).toBe(CHART);
  });

  it(
    "closes the fullscreen viewer on a backdrop click but not on a panel click",
    async () => {
      const { backdrop, panel } = await openFullscreen();
      fireEvent.click(panel);
      // Re-query the DOM: the captured backdrop reference stays truthy even
      // after React unmounts it, so it cannot prove the viewer is still open.
      expect(screen.queryByRole("dialog")).not.toBeNull();
      fireEvent.click(backdrop);
      expect(screen.queryByRole("dialog")).toBeNull();
    },
    RENDER_TEST_TIMEOUT_MS,
  );

  it(
    "keeps the inline source pane capped while the fullscreen viewer is open",
    async () => {
      const { container } = await openFullscreen();
      // The card is the first top-level node; the modal is its sibling.
      const card = container.firstElementChild!;
      // Both headers render the tabs; switch the inline card's own to Source.
      fireEvent.click(within(card as HTMLElement).getByRole("tab", { name: /source|源码/i }));
      // Only the modal stage may grow with its layout; the inline pane keeps the
      // card's height cap, or the conversation behind the backdrop would reflow.
      const inlinePane = card.querySelector("div.overflow-auto");
      expect(inlinePane).not.toBeNull();
      expect(inlinePane!.getAttribute("style")).toContain("480px");
    },
    RENDER_TEST_TIMEOUT_MS,
  );

  it(
    "keeps the zoom across a theme re-render of the same chart",
    async () => {
      const { panel } = await openFullscreen();
      // The readout doubles as the zoom display; one zoom-in press reads 125%.
      const readout = () => within(panel).getByRole("button", { name: /fit to screen|适应窗口/i });
      fireEvent.click(within(panel).getByRole("button", { name: /zoom in|放大/i }));
      expect(readout().textContent).toBe("125%");
      // Re-render the same chart for the dark palette: the zoom must survive it.
      // The disabled flag is read off the element directly: this suite has no
      // jest-dom matchers.
      const disabled = () => (readout() as HTMLButtonElement).disabled;
      try {
        document.documentElement.classList.add("dark");
        // Disabled first proves the re-render started; enabled again proves it
        // finished, so the assertion below cannot race the reset. The render
        // itself takes seconds, so neither window fits waitFor's default 1s.
        await waitFor(() => expect(disabled()).toBe(true), { timeout: RENDER_WAIT_TIMEOUT_MS });
        await waitFor(() => expect(disabled()).toBe(false), { timeout: RENDER_WAIT_TIMEOUT_MS });
        expect(readout().textContent).toBe("125%");
      } finally {
        document.documentElement.classList.remove("dark");
      }
    },
    2 * RENDER_WAIT_TIMEOUT_MS,
  );
});
