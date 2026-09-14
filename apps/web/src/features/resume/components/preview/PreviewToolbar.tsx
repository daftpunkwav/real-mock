"use client";

/**
 * @file PreviewToolbar.tsx
 * @description Filename, page index, zoom, fit-width, and download for PDF preview.
 */

import { Download, Maximize2, ZoomIn, ZoomOut } from "lucide-react";
import { useT } from "@/i18n";
import { ZOOM_STEP } from "./usePreviewViewport";

interface PreviewToolbarProps {
  name: string;
  isPdf: boolean;
  pageCount: number | null;
  currentPage: number;
  zoom: number;
  /** Measured container width; gates zoom controls when positive. */
  baseWidth: number;
  onZoom: (factor: number) => void;
  onFitWidth: () => void;
  downloadUrl: string;
}

/** Preview toolbar body: paging, zoom, and download actions. */
export function PreviewToolbar({
  name,
  isPdf,
  pageCount,
  currentPage,
  zoom,
  baseWidth,
  onZoom,
  onFitWidth,
  downloadUrl,
}: PreviewToolbarProps) {
  const t = useT("resume");
  const hasPages = isPdf && pageCount != null && pageCount > 0;
  return (
    <div className="flex items-center gap-3 border-b border-surface-border bg-surface-card px-4 py-2">
      <p className="min-w-0 flex-1 truncate text-[13px] font-semibold text-ink">{name}</p>
      {hasPages && (
        <span className="shrink-0 text-[11px] text-ink-subtle num-tabular">
          {t("preview.pages", { current: currentPage, total: pageCount })}
        </span>
      )}
      {hasPages && baseWidth > 0 && (
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            aria-label={t("preview.zoomOut")}
            className="btn-secondary !h-8 !w-8 !px-0"
            onClick={() => onZoom(1 / ZOOM_STEP)}
          >
            <ZoomOut size={13} />
          </button>
          <span className="w-11 select-none text-center font-mono text-[11px] text-ink-muted num-tabular">
            {Math.round(zoom * 100)}%
          </span>
          <button
            type="button"
            aria-label={t("preview.zoomIn")}
            className="btn-secondary !h-8 !w-8 !px-0"
            onClick={() => onZoom(ZOOM_STEP)}
          >
            <ZoomIn size={13} />
          </button>
          <button
            type="button"
            aria-label={t("preview.fitWidth")}
            className="btn-secondary !h-8 !w-8 !px-0"
            onClick={onFitWidth}
          >
            <Maximize2 size={13} />
          </button>
        </div>
      )}
      <a href={downloadUrl} className="btn-secondary !h-8 shrink-0 !px-3 !text-[12px]">
        <Download size={13} />
        {t("preview.download")}
      </a>
    </div>
  );
}
