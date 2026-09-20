/**
 * @file MermaidBlock.tsx
 * @description Render ```mermaid fences as SVG diagrams with a diagram/source
 * dual view, zoom controls, and a fullscreen viewer. Parse failures degrade to
 * the source view with a calm notice — mermaid's own error diagram is
 * suppressed (suppressErrorRendering) so a broken chart can never inject the
 * giant red "Syntax error in text" banner into the page. Diagrams re-render on
 * app theme changes and follow the light/dark palette.
 */

import { memo, useCallback, useEffect, useId, useState } from "react";
import {
  AlertTriangle,
  Check,
  Code,
  Copy,
  Image as ImageIcon,
  Maximize2,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useT } from "@/i18n";
import { copyTextToClipboard } from "@/lib/clipboard";
import {
  fitDiagramSvg,
  isErrorDiagramSvg,
  repairMermaidSubgraphs,
  sanitizeDiagramSvg,
} from "./diagramSvg";

/** Debounce re-renders while the chart streams in. */
const RENDER_DEBOUNCE_MS = 300;

/** Delay before a render failure surfaces its notice (lets streams settle). */
const ERROR_NOTICE_DELAY_MS = 1200;

/** Zoom steps in percent; index 2 (100%) is the default fit width. */
const ZOOM_STEPS = [50, 75, 100, 150, 200, 300] as const;
const DEFAULT_ZOOM_INDEX = 2;

/** Feedback duration for the copied state. */
const COPIED_RESET_MS = 1500;

function errorMessage(err: unknown): string {
  if (err instanceof Error && err.message) return err.message;
  try {
    return String(err);
  } catch {
    return "Unknown render error";
  }
}

function readDarkMode(): boolean {
  if (typeof document === "undefined") return false;
  return document.documentElement.classList.contains("dark");
}

export const MermaidBlock = memo(function MermaidBlock({ chart }: { chart: string }) {
  const t = useT("common");
  const [svg, setSvg] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [showNotice, setShowNotice] = useState(false);
  const [view, setView] = useState<"diagram" | "source">("diagram");
  const [zoomIndex, setZoomIndex] = useState(DEFAULT_ZOOM_INDEX);
  const [fullscreen, setFullscreen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [dark, setDark] = useState(false);
  const rawId = useId();
  const diagramId = `md-diagram-${rawId.replace(/[^a-zA-Z0-9]/g, "")}`;

  // Track the app theme (class-based dark mode) so diagrams match the palette.
  useEffect(() => {
    setDark(readDarkMode());
    const observer = new MutationObserver(() => setDark(readDarkMode()));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;
    setSvg(null);
    setFailure(null);
    setShowNotice(false);
    const source = chart.trim();
    if (!source) return;
    const timer = window.setTimeout(() => {
      void import("mermaid")
        .then(async ({ default: mermaid }) => {
          mermaid.initialize({
            startOnLoad: false,
            securityLevel: "strict",
            // Best-effort: reject on parse errors instead of resolving with
            // the red error-diagram SVG that used to flood the page. The
            // isErrorDiagramSvg content check below is the real guard and
            // works regardless of this flag.
            suppressErrorRendering: true,
            theme: readDarkMode() ? "dark" : "default",
            themeVariables: readDarkMode()
              ? {
                  fontFamily: "inherit",
                  primaryColor: "#1c2b3a",
                  primaryTextColor: "#e6edf3",
                  primaryBorderColor: "#6b93b8",
                  lineColor: "#8ba9c7",
                  secondaryColor: "#243447",
                  tertiaryColor: "#0d1117",
                  textColor: "#e6edf3",
                  mainBkg: "#16283f",
                  nodeBorder: "#6b93b8",
                  clusterBkg: "rgba(107,147,184,0.10)",
                  edgeLabelBackground: "#0d1117",
                }
              : { fontFamily: "inherit" },
            flowchart: { htmlLabels: true },
          });
          // Models sometimes emit invalid `subgraph` headers (bare CJK ids).
          // mermaid.parse() may still resolve while render() rejects (or
          // resolves with the error placeholder), so retry the whole
          // parse+render once with repaired syntax before degrading.
          const renderText = async (text: string): Promise<string> => {
            await mermaid.parse(text);
            const { svg: rendered } = await mermaid.render(diagramId, text);
            if (isErrorDiagramSvg(rendered)) {
              throw new Error("Diagram engine returned its error placeholder.");
            }
            return rendered;
          };
          let rendered: string;
          try {
            rendered = await renderText(source);
          } catch (firstErr) {
            const fixed = repairMermaidSubgraphs(source);
            if (fixed === source) throw firstErr;
            rendered = await renderText(fixed);
          }
          if (!cancelled) {
            setSvg(fitDiagramSvg(sanitizeDiagramSvg(rendered)));
            setFailure(null);
          }
        })
        .catch((err: unknown) => {
          // Parse/render failure (often a partial stream): stay on source.
          if (!cancelled) {
            setSvg(null);
            setFailure(errorMessage(err));
          }
        });
    }, RENDER_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [chart, diagramId, dark]);

  // Surface the failure notice only once the chart stops changing, so
  // streaming content does not flash error UI on every partial chunk.
  useEffect(() => {
    if (!failure) {
      setShowNotice(false);
      return;
    }
    const timer = window.setTimeout(() => setShowNotice(true), ERROR_NOTICE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [failure, chart]);

  // Escape closes the viewer; lock background scroll while it is open.
  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFullscreen(false);
    };
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [fullscreen]);

  const onCopy = useCallback(() => {
    void copyTextToClipboard(chart.trimEnd()).then((ok) => {
      if (!ok) return;
      setCopied(true);
      window.setTimeout(() => setCopied(false), COPIED_RESET_MS);
    });
  }, [chart]);

  const zoomPct = ZOOM_STEPS[Math.min(zoomIndex, ZOOM_STEPS.length - 1)] ?? 100;
  const canZoom = view === "diagram" && svg !== null;
  const source = chart.trimEnd();

  const diagramPane = (tall: boolean) => (
    <div
      className={`overflow-auto bg-surface-alt ${tall ? "max-h-[76vh]" : "max-h-[480px]"}`}
    >
      {svg ? (
        <div
          className={zoomPct <= 100 ? "mx-auto" : undefined}
          style={{ width: `${zoomPct}%`, minWidth: zoomPct <= 100 ? undefined : "100%" }}
          role="img"
          aria-label={`${t("code.diagram")}: ${chart.slice(0, 120)}`}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      ) : (
        <p className="p-6 text-center text-[13px] text-ink-subtle">
          {failure && showNotice ? t("code.diagramFailed") : t("state.loading")}
        </p>
      )}
    </div>
  );

  const sourcePane = (tall: boolean) => (
    <div className={tall ? "max-h-[76vh] overflow-auto" : undefined}>
      {failure && showNotice && (
        <div className="flex items-start gap-2 border-b border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[12px] text-amber-700 dark:text-amber-300">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <div className="min-w-0">
            <p>{t("code.diagramFailed")}</p>
            <details className="mt-1">
              <summary className="cursor-pointer underline underline-offset-2">
                {t("code.errorDetail")}
              </summary>
              <p className="mt-1 font-mono text-[11px] break-all whitespace-pre-wrap">
                {failure}
              </p>
            </details>
          </div>
        </div>
      )}
      <pre className="overflow-x-auto bg-surface-alt p-3">
        <code className="block font-mono text-xs leading-relaxed whitespace-pre-wrap text-ink">
          {source}
        </code>
      </pre>
    </div>
  );

  const controls = (
    <div className="flex items-center gap-0.5">
      <button
        type="button"
        onClick={() => setZoomIndex((i) => Math.max(0, i - 1))}
        disabled={!canZoom || zoomIndex <= 0}
        className="rounded p-1.5 text-ink-subtle transition-colors hover:bg-surface-alt hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
        aria-label={t("code.zoomOut")}
        title={t("code.zoomOut")}
      >
        <ZoomOut size={14} />
      </button>
      <button
        type="button"
        onClick={() => setZoomIndex(DEFAULT_ZOOM_INDEX)}
        disabled={!canZoom}
        className="min-w-[2.75rem] rounded px-1 py-1 font-mono text-[11px] text-ink-subtle transition-colors hover:bg-surface-alt hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
        aria-label={t("code.zoomReset")}
        title={t("code.zoomReset")}
      >
        {zoomPct}%
      </button>
      <button
        type="button"
        onClick={() =>
          setZoomIndex((i) => Math.min(ZOOM_STEPS.length - 1, i + 1))
        }
        disabled={!canZoom || zoomIndex >= ZOOM_STEPS.length - 1}
        className="rounded p-1.5 text-ink-subtle transition-colors hover:bg-surface-alt hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
        aria-label={t("code.zoomIn")}
        title={t("code.zoomIn")}
      >
        <ZoomIn size={14} />
      </button>
      <button
        type="button"
        onClick={() => setFullscreen(true)}
        disabled={svg === null}
        className="rounded p-1.5 text-ink-subtle transition-colors hover:bg-surface-alt hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
        aria-label={t("code.fullscreen")}
        title={t("code.fullscreen")}
      >
        <Maximize2 size={14} />
      </button>
      <button
        type="button"
        onClick={onCopy}
        className="flex items-center gap-1 rounded px-1.5 py-1 text-[11px] text-ink-subtle transition-colors hover:bg-surface-alt hover:text-ink"
        aria-label={copied ? t("code.copied") : t("code.copy")}
        title={copied ? t("code.copied") : t("code.copy")}
      >
        {copied ? <Check size={12} /> : <Copy size={12} />}
      </button>
    </div>
  );

  return (
    <>
      <div className="my-2 overflow-hidden rounded-md border border-surface-border">
        <div className="flex items-center justify-between gap-2 border-b border-surface-border bg-surface-muted px-2 py-1">
          <div
            className="flex items-center rounded bg-surface-alt p-0.5"
            role="tablist"
            aria-label={t("code.diagram")}
          >
            <button
              type="button"
              role="tab"
              aria-selected={view === "diagram"}
              onClick={() => setView("diagram")}
              className={`flex items-center gap-1 rounded px-2 py-1 text-[11px] transition-colors ${
                view === "diagram"
                  ? "bg-surface-muted font-medium text-ink"
                  : "text-ink-subtle hover:text-ink"
              }`}
            >
              <ImageIcon size={12} />
              {t("code.diagram")}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={view === "source"}
              onClick={() => setView("source")}
              className={`flex items-center gap-1 rounded px-2 py-1 text-[11px] transition-colors ${
                view === "source"
                  ? "bg-surface-muted font-medium text-ink"
                  : "text-ink-subtle hover:text-ink"
              }`}
            >
              <Code size={12} />
              {t("code.source")}
            </button>
          </div>
          {controls}
        </div>
        {view === "diagram" ? diagramPane(false) : sourcePane(false)}
      </div>
      {fullscreen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onClick={() => setFullscreen(false)}
          role="dialog"
          aria-modal="true"
          aria-label={t("code.diagram")}
        >
          <div
            className="flex max-h-full w-full max-w-6xl flex-col overflow-hidden rounded-lg border border-surface-border bg-surface"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-2 border-b border-surface-border bg-surface-muted px-3 py-2">
              <span className="truncate text-[13px] font-medium text-ink">
                {t("code.diagram")}
              </span>
              <div className="flex items-center gap-0.5">
                {controls}
                <button
                  type="button"
                  onClick={() => setFullscreen(false)}
                  className="rounded p-1.5 text-ink-subtle transition-colors hover:bg-surface-alt hover:text-ink"
                  aria-label={t("action.close")}
                >
                  <X size={14} />
                </button>
              </div>
            </div>
            <div className="overflow-auto bg-surface-alt">
              {view === "diagram" ? diagramPane(true) : sourcePane(true)}
            </div>
          </div>
        </div>
      )}
    </>
  );
});
