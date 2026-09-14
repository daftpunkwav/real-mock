"use client";

import { AlertCircle, RefreshCw } from "lucide-react";
import { getEnv } from "@/lib/env";
import { useT } from "@/i18n";

/** API load failure: error text + backend URL hint + optional retry. */
export function LoadError({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  const t = useT("common");
  let backendHint = t("load.hint.notConfigured");
  try {
    const env = getEnv();
    backendHint = env.STREAM_API_BASE || env.API_BASE;
  } catch {
    backendHint = t("load.hint.checkEnv");
  }

  return (
    <div className="alert alert-error">
      <span className="icon-badge icon-badge-danger shrink-0">
        <AlertCircle size={16} strokeWidth={1.75} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-semibold">{t("load.failed")}</p>
        <p className="mt-1 break-words text-[13px] leading-relaxed opacity-90">
          {message}
        </p>
        <p className="mt-2 text-[11px] leading-relaxed opacity-70">
          {t("load.backendHintPrefix")}
          <code className="mx-1 rounded border border-[var(--danger)]/30 bg-surface-card px-1.5 py-0.5 font-mono text-[11px] text-[var(--danger-ink)]">
            {backendHint}
          </code>
          {t("load.backendHintSuffix")}
        </p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--danger)]/30 bg-surface-card px-3 text-[12px] font-medium text-[var(--danger-ink)] transition-colors hover:bg-surface-alt"
          >
            <RefreshCw size={13} />
            {t("action.retry")}
          </button>
        )}
      </div>
    </div>
  );
}
