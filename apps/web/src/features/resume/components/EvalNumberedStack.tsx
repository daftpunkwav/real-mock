"use client";

/**
 * @file EvalNumberedStack.tsx
 * @description Numbered stack of evaluation items (P1 / Q1 prefixes).
 *
 * `onSend` (when provided) renders a per-row "send to prep" action; the item
 * text is passed through untouched so the caller owns any wrapping.
 */

import { SendHorizontal } from "lucide-react";
import { useRouter } from "next/navigation";
import { useT } from "@/i18n";
import { buildPrepDeepLink } from "../sendToPrep";
import { EvalRichText } from "./EvalRichText";

export function EvalNumberedStack({
  title,
  items,
  prefix,
  resumeId,
}: {
  title: string;
  items: string[];
  prefix: string;
  /** Owning resume id; enables the per-row "send to prep" action. */
  resumeId?: number | null;
}) {
  const t = useT("resume");
  const router = useRouter();
  return (
    <section className="eval-section">
      <span className="eval-label">{title}</span>
      <div className="eval-q-stack">
        {items.map((q, i) => (
          <div key={i} className={`eval-q ${q.trim() ? "has-actions" : ""}`}>
            <span className="eval-q-idx">
              {prefix}
              {i + 1}
            </span>
            <p className="eval-prose eval-prose-sm !max-w-none m-0">
              <EvalRichText text={q} />
            </p>
            {q.trim() ? (
              <button
                type="button"
                onClick={() => {
                  router.push(
                    buildPrepDeepLink(resumeId ?? null, t("sendToPrep.template", { question: q })),
                  );
                }}
                title={t("sendToPrep.action")}
                aria-label={t("sendToPrep.action")}
                className="shrink-0 self-center rounded-md border border-surface-border p-1.5 text-ink-subtle transition-colors hover:border-[var(--primary)] hover:text-[var(--primary)]"
              >
                <SendHorizontal size={12} />
              </button>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}
