"use client";

/**
 * @file MermaidBlock.tsx
 * @description Render ```mermaid fences with a diagram/source dual view, zoom
 * controls and a fullscreen viewer. Owns UI state only — rendering lives in
 * diagramRender.ts, sizing in DiagramViewport.tsx, the palette in
 * diagramTheme.ts.
 *
 * Parse failures degrade to the source view with a calm notice; mermaid's own
 * error diagram is suppressed so a broken chart can never inject the giant red
 * "Syntax error in text" banner into the page. Diagrams re-render on app theme
 * changes and follow the light/dark palette.
 */

import { memo, useCallback, useEffect, useId, useMemo, useState } from "react";
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
import { DiagramViewport } from "./DiagramViewport";
import { readSvgViewBox } from "./diagramSvg";
import { renderDiagramSvg } from "./diagramRender";
import { ZOOM_MAX, ZOOM_MIN, clampZoom, zoomIn, zoomOut } from "./diagramZoom";

/** Debounce re-renders while the chart streams in. */
const RENDER_DEBOUNCE_MS = 300;

/** Delay before a render failure surfaces its notice (lets streams settle). */
const ERROR_NOTICE_DELAY_MS = 1200;

/** Height budget for the inline diagram, in px. */
const INLINE_MAX_HEIGHT_PX = 480;

/** Feedback duration for the copied state. */
const COPIED_RESET_MS = 1500;

const ICON_BUTTON =
  "rounded p-1.5 text-ink-subtle transition-colors hover:bg-surface-alt hover:text-ink disabled:cursor-not-allowed disabled:opacity-40";

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
  const [zoom, setZoom] = useState(1);
  const [fullscreen, setFullscreen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [dark, setDark] = useState(false);
  // mermaid keys its stylesheet, gradients and node ids on this id, so it has to
  // be unique per block and stay valid inside a CSS selector.
  const diagramId = `md-diagram-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;

  // Track the app theme (class-based dark mode) so diagrams match the palette.
  useEffect(() => {
    setDark(readDarkMode());
    const observer = new MutationObserver(() => setDark(readDarkMode()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
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
      void renderDiagramSvg({ chart: source, id: diagramId, dark })
        .then((rendered) => {
          if (cancelled) return;
          setSvg(rendered);
          setFailure(null);
          // A re-rendered chart gets a clean stage instead of the old zoom.
          setZoom(1);
        })
        .catch((err: unknown) => {
          // Parse/render failure (often a partial stream): stay on source.
          if (cancelled) return;
          setSvg(null);
          setFailure(errorMessage(err));
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

  const natural = useMemo(() => (svg ? readSvgViewBox(svg) : null), [svg]);
  const source = chart.trimEnd();
  const canZoom = view === "diagram" && svg !== null;
  const diagramLabel = `${t("code.diagram")}: ${chart.slice(0, 120)}`;

  /** Diagram or source, at the given height budget. */
  const body = () => {
    // Source first: when a chart never rendered, or failed, the source is the
    // only thing left to show, so the Source tab must not fall back to the
    // loading paragraph just because there is no svg.
    if (view === "source") {
      return (
        // The fullscreen stage already scrolls, so it needs no cap of its own.
        <div
          className="overflow-auto"
          style={{ maxHeight: fullscreen ? undefined : INLINE_MAX_HEIGHT_PX }}
        >
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
    }
    if (!svg) {
      return (
        <p className="bg-surface-alt p-6 text-center text-[13px] text-ink-subtle">
          {failure && showNotice ? t("code.diagramFailed") : t("state.loading")}
        </p>
      );
    }
    return (
      <DiagramViewport
        svg={svg}
        natural={natural}
        zoom={zoom}
        onZoomChange={setZoom}
        // The inline block has a constant budget; the fullscreen stage is sized
        // by the modal layout, so the viewport measures it directly. Doing that
        // in the viewport rather than here also keeps the layout hook out of a
        // component that is server rendered.
        maxHeight={fullscreen ? "parent" : INLINE_MAX_HEIGHT_PX}
        label={diagramLabel}
      />
    );
  };

  const tabs = (
    <div
      className="flex items-center rounded bg-surface-alt p-0.5"
      role="tablist"
      aria-label={t("code.diagram")}
    >
      {(
        [
          { id: "diagram", label: t("code.diagram"), Icon: ImageIcon },
          { id: "source", label: t("code.source"), Icon: Code },
        ] as const
      ).map(({ id, label, Icon }) => (
        <button
          key={id}
          type="button"
          role="tab"
          aria-selected={view === id}
          onClick={() => setView(id)}
          className={`flex items-center gap-1 rounded px-2 py-1 text-[11px] transition-colors ${
            view === id ? "bg-surface-muted font-medium text-ink" : "text-ink-subtle hover:text-ink"
          }`}
        >
          <Icon size={12} />
          {label}
        </button>
      ))}
    </div>
  );

  const controls = (
    <>
      <button
        type="button"
        onClick={() => setZoom(zoomOut)}
        disabled={!canZoom || zoom <= ZOOM_MIN}
        className={ICON_BUTTON}
        aria-label={t("code.zoomOut")}
        title={t("code.zoomOut")}
      >
        <ZoomOut size={14} />
      </button>
      {/* Readout doubles as the fit control: 100% means "whole diagram visible". */}
      <button
        type="button"
        onClick={() => setZoom(1)}
        disabled={!canZoom}
        className="min-w-[2.75rem] rounded px-1 py-1 font-mono text-[11px] text-ink-subtle transition-colors hover:bg-surface-alt hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
        aria-label={t("code.fitToScreen")}
        title={t("code.fitToScreen")}
      >
        {Math.round(clampZoom(zoom) * 100)}%
      </button>
      <button
        type="button"
        onClick={() => setZoom(zoomIn)}
        disabled={!canZoom || zoom >= ZOOM_MAX}
        className={ICON_BUTTON}
        aria-label={t("code.zoomIn")}
        title={t("code.zoomIn")}
      >
        <ZoomIn size={14} />
      </button>
      <button
        type="button"
        onClick={() => setFullscreen(true)}
        disabled={svg === null}
        className={ICON_BUTTON}
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
    </>
  );

  return (
    <>
      <div className="my-2 overflow-hidden rounded-md border border-surface-border">
        <div className="flex items-center justify-between gap-2 border-b border-surface-border bg-surface-muted px-2 py-1">
          {tabs}
          <div className="flex items-center gap-0.5">{controls}</div>
        </div>
        {body()}
      </div>
      {fullscreen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          // Closing on a backdrop click is decided here rather than by stopping
          // propagation on the panel: one handler, and no click handler bolted
          // onto the non-interactive panel element.
          onClick={(event) => {
            if (event.target === event.currentTarget) setFullscreen(false);
          }}
          role="dialog"
          aria-modal="true"
          aria-label={t("code.diagram")}
        >
          <div
            // h-full makes the panel a definite height so the stage below it is
            // sized by the leftover space, not by the diagram it contains; that
            // is what lets the stage be measured for the fit budget. It also
            // replaces the old window-height fraction, which ignored the header
            // and the overlay padding and so overflowed a short window.
            className="flex h-full max-h-full w-full max-w-6xl flex-col overflow-hidden rounded-lg border border-surface-border bg-surface"
          >
            <div className="flex shrink-0 items-center justify-between gap-2 border-b border-surface-border bg-surface-muted px-3 py-2">
              <span className="truncate text-[13px] font-medium text-ink">{t("code.diagram")}</span>
              <div className="flex items-center gap-2">
                {tabs}
                <div className="flex items-center gap-0.5">{controls}</div>
                <button
                  type="button"
                  onClick={() => setFullscreen(false)}
                  className={ICON_BUTTON}
                  aria-label={t("action.close")}
                >
                  <X size={14} />
                </button>
              </div>
            </div>
            {/* min-h-0 lets the flex child shrink below its content; overflow
                auto scrolls the zoomed diagram here, where trapping the scroll
                is correct because the page behind is locked. */}
            <div className="min-h-0 flex-1 overflow-auto">{body()}</div>
          </div>
        </div>
      )}
    </>
  );
});
