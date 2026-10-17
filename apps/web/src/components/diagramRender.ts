/**
 * @file diagramRender.ts
 * @description The mermaid render pipeline for one chart: lazy-load mermaid,
 * apply the app theme, parse and render with a single syntax-repair retry, and
 * post-process the resulting SVG. Framework-free so the component only owns UI
 * state, and so the pipeline can be exercised directly in tests.
 *
 * Constraints:
 * - This module must not render anything to the screen and must not hold UI
 *   state; callers own the debounce and the theme toggle.
 * - mermaid is imported lazily inside the call, not at module scope, so the
 *   ~1 MB diagram engine never lands in the initial bundle.
 * - Syntax repair belongs to diagramSource.ts; SVG post-processing belongs to
 *   diagramSvg.ts. Neither is duplicated here.
 */

import { fitDiagramSvg, isErrorDiagramSvg, sanitizeDiagramSvg } from "./diagramSvg";
import { repairMermaidSource } from "./diagramSource";
import { buildDiagramTheme } from "./diagramTheme";

export interface RenderDiagramOptions {
  /** Chart source as written in the fence. */
  chart: string;
  /** Unique DOM id; mermaid keys its stylesheet and generated node ids on it. */
  id: string;
  /** Re-render for the dark palette when true. */
  dark: boolean;
}

/**
 * Serializes every mermaid call in this process.
 *
 * `mermaid.initialize` writes to one module-level configuration and both
 * parse() and render() read from it, so two overlapping invocations — a theme
 * toggle landing while a previous chart is still rendering, or two diagrams in
 * one conversation — would let the later configuration decide the earlier
 * chart's palette. Chaining each run onto the previous one makes the
 * initialize/parse/render sequence atomic from mermaid's point of view.
 *
 * A rejected run must not break the chain, hence the separate rejection
 * handler: it keeps the failure owned by its own caller and still resolves.
 */
let renderQueue: Promise<unknown> = Promise.resolve();

/**
 * Render one chart to display-ready SVG.
 *
 * Rejects on a parse or render failure; the caller decides how to surface it.
 */
export function renderDiagramSvg(options: RenderDiagramOptions): Promise<string> {
  const run = renderQueue.then(() => renderPass(options));
  // The queue resolves for the next run either way; the failure still travels
  // to this caller's own promise.
  renderQueue = run.catch(() => undefined);
  return run;
}

/** One initialize/parse/render pass; see renderDiagramSvg for the queueing. */
async function renderPass({ chart, id, dark }: RenderDiagramOptions): Promise<string> {
  const { default: mermaid } = await import("mermaid");
  mermaid.initialize({
    startOnLoad: false,
    // Mermaid's own boundary: DOMPurify on labels, no click handlers, no
    // navigation. The sanitize pass below only shrinks what is left over.
    securityLevel: "strict",
    // Best-effort: reject on parse errors instead of resolving with the red
    // error-diagram SVG. The isErrorDiagramSvg content check is the real guard
    // and works regardless of this flag.
    suppressErrorRendering: true,
    ...buildDiagramTheme(dark),
  });
  // Models sometimes pack the flowchart direction and the first node onto one
  // line, or emit invalid `subgraph` headers (bare CJK ids). mermaid.parse()
  // may still resolve while render() rejects (or resolves with the error
  // placeholder), so retry the whole parse+render once with repaired syntax
  // before degrading to the source view.
  const renderText = async (text: string): Promise<string> => {
    await mermaid.parse(text);
    const { svg } = await mermaid.render(id, text);
    if (isErrorDiagramSvg(svg)) {
      throw new Error("Diagram engine returned its error placeholder.");
    }
    return svg;
  };
  let rendered: string;
  try {
    rendered = await renderText(chart);
  } catch (firstError) {
    const repaired = repairMermaidSource(chart);
    if (repaired === chart) throw firstError;
    rendered = await renderText(repaired);
  }
  return fitDiagramSvg(sanitizeDiagramSvg(rendered));
}
