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
 * The newest request per diagram id.
 *
 * While a chart streams, each debounce expiry queues a render; with a slow
 * render in flight, obsolete requests pile up behind it in the queue and each
 * would run to completion only to be discarded by its caller, delaying the
 * chart the user is actually looking at. Only the newest request per id is
 * worth a render pass; the rest are skipped before mermaid is touched.
 */
const latestTicketById = new Map<string, symbol>();

/**
 * Render one chart to display-ready SVG.
 *
 * Rejects on a parse or render failure. Also rejects with a "superseded"
 * error once a newer chart is queued for the same id — that failure is safe
 * for the caller to drop, because it means the caller has already moved on to
 * the newer chart.
 */
export function renderDiagramSvg(options: RenderDiagramOptions): Promise<string> {
  const ticket = Symbol();
  latestTicketById.set(options.id, ticket);
  const run = renderQueue.then(() => {
    if (latestTicketById.get(options.id) !== ticket) {
      // A newer chart for this id arrived; its caller owns the render now.
      throw new Error("Diagram render superseded by a newer chart.");
    }
    return renderPass(options);
  });
  // The queue resolves for the next run either way; the failure still travels
  // to this caller's own promise.
  renderQueue = run.catch(() => undefined);
  // Drop the bookkeeping once the newest request for this id settles, so the
  // map does not grow with every diagram ever rendered.
  return run.finally(() => {
    if (latestTicketById.get(options.id) === ticket) latestTicketById.delete(options.id);
  });
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
    // htmlLabels has to resist chart directives: a %%{init}%% block may not
    // re-enable HTML labels, or every label returns to a <foreignObject> that
    // the sanitize pass strips. Keys in `secure` survive directives; the
    // mermaid defaults are restated so the list is extended, not replaced.
    secure: [
      "secure",
      "securityLevel",
      "startOnLoad",
      "maxTextSize",
      "suppressErrorRendering",
      "maxEdges",
      "htmlLabels",
    ],
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
