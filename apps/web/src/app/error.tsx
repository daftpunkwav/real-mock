"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, RotateCw, Home } from "lucide-react";
import { useT } from "@/i18n";

interface Props {
  error: Error & { digest?: string };
  reset: () => void;
}

/**
 * Route-segment Error Boundary.
 *
 * - Render errors inside this segment land here (root layout errors need global-error.tsx);
 * - Event callbacks and async errors are outside this boundary;
 * - ``reset`` re-renders the segment after the error;
 * - Shows ``digest`` (server-generated) for troubleshooting.
 */
// NOTE: segment-level boundary (file error.tsx); root errors need global-error.tsx.
export default function SegmentError({ error, reset }: Props) {
  const router = useRouter();
  const t = useT("common");

  useEffect(() => {
    console.error("[app/error]", error);
  }, [error]);

  return (
    <main className="flex min-h-[70vh] flex-col items-center justify-center px-6 text-center">
      <span className="empty-state-icon !bg-[var(--warning-soft)] !text-[var(--warning-ink)]">
        <AlertTriangle size={24} />
      </span>
      <p className="page-eyebrow mt-4">{t("err.eyebrow")}</p>
      <h1 className="mt-1 text-[22px] font-semibold tracking-tight text-ink">{t("err.title")}</h1>
      <p className="mt-2 max-w-md text-[13px] leading-relaxed text-ink-muted">
        {error.message || t("err.unknown")}
        {error.digest && (
          <span className="mt-2 block font-mono text-[11px] text-ink-subtle">
            {t("err.trace", { digest: error.digest })}
          </span>
        )}
      </p>
      <div className="mt-7 flex flex-wrap justify-center gap-2.5">
        <button type="button" onClick={() => reset()} className="btn-primary">
          <RotateCw size={14} /> {t("action.retry")}
        </button>
        <button type="button" onClick={() => router.push("/")} className="btn-secondary">
          <Home size={14} /> {t("action.backHome")}
        </button>
      </div>
    </main>
  );
}
