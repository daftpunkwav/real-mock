"use client";

/**
 * @file ResumeFilePreview.tsx
 * @description Original-file preview page: PDF PNG pages or txt/md text.
 *
 * Query contract: previewRoute. Viewport: usePreviewViewport.
 */

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { FileWarning, Download } from "lucide-react";
import { Spinner } from "@/components/Spinner";
import { useT } from "@/i18n";
import { resumeHttp } from "@/lib/api/clients";
import { useAlignedBackendUrl } from "@/lib/api/useAlignedBackendUrl";
import { parseResumePreviewParams } from "../previewRoute";
import { usePreviewViewport } from "./preview/usePreviewViewport";
import { PreviewToolbar } from "./preview/PreviewToolbar";

/**
 * Original-file preview: PDF pages as PNG images, or raw text.
 */
export function ResumeFilePreview() {
  const t = useT("resume");
  const params = useSearchParams();
  const { id, name, type } = parseResumePreviewParams(params, t("preview.nameFallback"));
  const isPdf = type === "pdf";
  const isText = type === "txt" || type === "md";
  // Hydration-safe: first render matches SSR; loopback host aligns after mount.
  const downloadUrl = useAlignedBackendUrl(resumeHttp.resumeFilePath(id, true));

  const [pageCount, setPageCount] = useState<number | null>(null);
  const [text, setText] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const viewport = usePreviewViewport();

  useEffect(() => {
    if (!id || !isPdf) return;
    let cancelled = false;
    resumeHttp
      .resumePagesMeta(id)
      .then((meta) => {
        if (!cancelled) setPageCount(meta.pages);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [id, isPdf]);

  useEffect(() => {
    if (!id || !isText) return;
    let cancelled = false;
    resumeHttp
      .resumeFileText(id)
      .then((t) => {
        if (!cancelled) setText(t);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [id, isText]);

  const renderable = isPdf || isText;
  const notRenderable = !id || !renderable || failed;
  const { scrollerRef, pageRefs, zoom, baseWidth, currentPage, dragging, zoomAt, setZoom, onScroll, panProps } = viewport;

  return (
    <div className="flex h-dvh flex-col bg-surface-alt">
      {/* Toolbar with filename, paging, zoom, and download. */}
      <PreviewToolbar
        name={name}
        isPdf={isPdf}
        pageCount={pageCount}
        currentPage={currentPage}
        zoom={zoom}
        baseWidth={baseWidth}
        onZoom={(factor) => zoomAt(factor, 0, 0)}
        onFitWidth={() => setZoom(1)}
        downloadUrl={downloadUrl}
      />

      <div ref={scrollerRef} onScroll={onScroll} className="min-h-0 flex-1 overflow-auto">
      {notRenderable ? (
        <div className="flex flex-col items-center justify-center gap-3 py-32 text-[13px] text-ink-muted">
          <FileWarning size={20} />
          <p>{failed ? t("preview.loadFailed") : t("preview.unsupported")}</p>
          <a href={downloadUrl} className="btn-primary !h-8 !px-3 !text-[12px]">
            <Download size={13} />
            {t("preview.downloadFile")}
          </a>
        </div>
      ) : isText ? (
        text == null ? (
          <Loading />
        ) : (
          <div className="mx-auto max-w-4xl p-5">
            <pre className="whitespace-pre-wrap text-[13px] leading-relaxed text-ink-muted">{text}</pre>
          </div>
        )
      ) : pageCount == null || baseWidth <= 0 ? (
        <Loading />
      ) : (
        <div
          {...panProps}
          className={`mx-auto w-fit p-4 ${dragging ? "cursor-grabbing select-none" : "cursor-grab"}`}
        >
          <div className="flex flex-col items-center gap-5">
            {Array.from({ length: pageCount }, (_, i) => (
              <PreviewPageImage
                key={i + 1}
                id={id}
                page={i + 1}
                name={name}
                width={Math.round(baseWidth * zoom)}
                registerRef={(el) => {
                  pageRefs.current[i] = el;
                }}
              />
            ))}
          </div>
        </div>
      )}
      </div>
    </div>
  );
}

/** One PDF page image with a hydration-safe src (hook per page). */
function PreviewPageImage({
  id,
  page,
  name,
  width,
  registerRef,
}: {
  id: number;
  page: number;
  name: string;
  width: number;
  registerRef: (el: HTMLImageElement | null) => void;
}) {
  const t = useT("resume");
  const src = useAlignedBackendUrl(resumeHttp.resumePageImagePath(id, page));
  // Use a plain img for dynamic page PNGs.
  // eslint-disable-next-line @next/next/no-img-element
  return (
    <img
      ref={registerRef}
      src={src}
      alt={t("preview.pageAlt", { name, page })}
      style={{ width, maxWidth: "none" }}
      className="bg-white shadow-md"
      loading="lazy"
      draggable={false}
    />
  );
}

function Loading() {
  const t = useT("resume");
  return (
    <div className="flex items-center justify-center gap-2 py-32 text-[13px] text-ink-muted">
      <Spinner />
      {t("page.loading")}
    </div>
  );
}
