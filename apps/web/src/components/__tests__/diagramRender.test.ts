// @vitest-environment jsdom
/**
 * Render pipeline: the chart's labels must survive both mermaid's rendering and
 * the XSS pass, and the result must be sized by the wrapper rather than by
 * mermaid's own inline max-width.
 *
 * mermaid measures text through SVG layout APIs that jsdom does not implement,
 * so the polyfill below stands in for the browser's text metrics. Its exact
 * numbers do not matter — only that layout can run.
 */

import { beforeAll, describe, expect, it } from "vitest";

import { renderDiagramSvg } from "../diagramRender";

const CHART = `flowchart TB
    A["请求进入"] --> B["限流：单实例/租户配额"]
    B --> C{"熔断状态"}
    C -->|"OPEN"| D["直接降级，不重试"]
`;

beforeAll(() => {
  const prototype = window.SVGElement.prototype as unknown as Record<string, unknown>;
  prototype.getBBox = function getBBox(this: SVGElement) {
    const text = this.textContent ?? "";
    return { x: 0, y: 0, width: text.length * 8, height: 20 };
  };
  prototype.getComputedTextLength = function getComputedTextLength(this: SVGElement) {
    return (this.textContent ?? "").length * 8;
  };
});

describe("renderDiagramSvg", () => {
  it("keeps node and edge labels in the rendered output", async () => {
    const svg = await renderDiagramSvg({ chart: CHART, id: "diagram-labels", dark: false });

    // Labels must be real SVG text: htmlLabels would put them in a
    // <foreignObject>, which the XSS pass strips, leaving bare shapes.
    expect(svg).not.toContain("<foreignObject");
    expect(svg).toContain("<text");
    expect(svg).toContain("请求进入");
    expect(svg).toContain("限流：单实例/租户配额");
    expect(svg).toContain("OPEN");
  }, 30_000);

  it("leaves the rendered size to the wrapper", async () => {
    const svg = await renderDiagramSvg({ chart: CHART, id: "diagram-size", dark: false });
    const root = svg.slice(0, svg.indexOf(">") + 1);

    // mermaid emits width="100%" plus an inline max-width capping the diagram
    // at its natural size. Exactly one style attribute must remain: a duplicate
    // is dropped by the HTML parser and the original would keep winning.
    expect(root).toContain('style="display:block;width:100%;height:100%"');
    expect(root.match(/style="/g)).toHaveLength(1);
    expect(root).not.toContain("max-width");
    expect(root).not.toMatch(/\s(?:width|height)="/);
    expect(root).toContain("viewBox");
  }, 30_000);

  it("emits the dark palette for the dark theme", async () => {
    const light = await renderDiagramSvg({ chart: CHART, id: "diagram-light", dark: false });
    const dark = await renderDiagramSvg({ chart: CHART, id: "diagram-dark", dark: true });
    // Both must render the chart; what tells the palettes apart is the colour.
    expect(light).toContain("请求进入");
    expect(dark).toContain("请求进入");
    // Node fill: the light token #e8f0fe against the dark one #1c2b3a.
    expect(light).toContain("fill:#e8f0fe");
    expect(dark).toContain("fill:#1c2b3a");
    expect(dark).not.toContain("fill:#e8f0fe");
  }, 30_000);

  it("serializes overlapping renders so a theme switch cannot repaint a chart", async () => {
    // Both run without awaiting in between: the second initialize would
    // otherwise land while the first render is still in flight and decide its
    // palette.
    const [light, dark] = await Promise.all([
      renderDiagramSvg({ chart: CHART, id: "parallel-light", dark: false }),
      renderDiagramSvg({ chart: CHART, id: "parallel-dark", dark: true }),
    ]);
    expect(light).toContain("fill:#e8f0fe");
    expect(dark).toContain("fill:#1c2b3a");
  }, 30_000);

  it("skips a queued render once a newer chart arrives for the same id", async () => {
    // Queue two charts for one id without awaiting: the stale run must reject
    // without rendering, instead of finishing an obsolete pass that its caller
    // already stopped waiting for and delaying the chart on screen.
    const stale = renderDiagramSvg({
      chart: 'flowchart LR\n  X["stale"] --> Y["stale"]',
      id: "diagram-superseded",
      dark: false,
    });
    const fresh = renderDiagramSvg({ chart: CHART, id: "diagram-superseded", dark: false });
    await expect(stale).rejects.toThrow(/superseded/i);
    expect(await fresh).toContain("请求进入");
  }, 30_000);

  it("rejects on a chart mermaid cannot parse, even after repair", async () => {
    await expect(
      renderDiagramSvg({
        chart: "flowchart TB\n  this is not a chart",
        id: "diagram-bad",
        dark: false,
      }),
    ).rejects.toThrow();
  }, 30_000);
});
