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

beforeAll(() => {
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
});

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
    { timeout: 20_000 },
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

  it("closes the fullscreen viewer on a backdrop click but not on a panel click", async () => {
    const { backdrop, panel } = await openFullscreen();
    fireEvent.click(panel);
    expect(backdrop).toBeTruthy();
    fireEvent.click(backdrop);
    expect(screen.queryByRole("dialog")).toBeNull();
  }, 30_000);

  it("keeps the inline source pane capped while the fullscreen viewer is open", async () => {
    const { container } = await openFullscreen();
    // Both headers render the tabs; switch the inline card's own to Source.
    fireEvent.click(within(container.children[0]).getByRole("tab", { name: /source|源码/i }));
    // Only the modal stage may grow with its layout; the inline pane keeps the
    // card's height cap, or the conversation behind the backdrop would reflow.
    const inlinePane = container.children[0].querySelector("div.overflow-auto");
    expect(inlinePane).not.toBeNull();
    expect(inlinePane!.getAttribute("style")).toContain("480px");
  }, 30_000);
});
