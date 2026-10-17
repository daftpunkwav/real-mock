// @vitest-environment jsdom
/**
 * @file MermaidBlock.test.tsx
 * @description The dual view stays honest before a diagram exists: selecting
 * Source must show the chart source, which is the only thing left to show
 * while a chart is still rendering or has failed outright.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
});
