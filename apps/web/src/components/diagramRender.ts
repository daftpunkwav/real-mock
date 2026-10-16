/**
 * @file diagramRender.ts
 * @description The mermaid render pipeline for one chart: lazy-load mermaid,
 * apply the app theme, parse and render with a single syntax-repair retry, and
 * post-process the resulting SVG. Framework-free so the component only owns UI
 * state, and so the pipeline can be exercised directly in tests.
 *
 * Constraints:
 * - This module must not render anything to the screen and must not hold state;
 *   callers own the debounce and the theme toggle.
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
 * Render one chart to display-ready SVG.
 *
 * Rejects on a parse or render failure; the caller decides how to surface it.
 */
export async function renderDiagramSvg({ chart, id, dark }: RenderDiagramOptions): Promise<string> {
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
