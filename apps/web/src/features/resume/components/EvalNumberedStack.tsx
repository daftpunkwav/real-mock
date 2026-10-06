"use client";

/**
 * @file EvalNumberedStack.tsx
 * @description Numbered stack of evaluation items (P1 / Q1 prefixes).
 *
 * A nonblank item together with `resumeId` enables the per-row "send to prep"
 * action; item text is passed through untouched.
 */

import { EvalRichText } from "./EvalRichText";
import { SendToPrepButton } from "./SendToPrepButton";

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
  return (
    <section className="eval-section">
      <span className="eval-label">{title}</span>
      <div className="eval-q-stack">
        {items.map((q, i) => (
          <div key={`${i}-${q}`} className={`eval-q ${q.trim() ? "has-actions" : ""}`}>
            <span className="eval-q-idx">
              {prefix}
              {i + 1}
            </span>
            <p className="eval-prose eval-prose-sm !max-w-none m-0">
              <EvalRichText text={q} />
            </p>
            {q.trim() ? <SendToPrepButton question={q} resumeId={resumeId ?? null} /> : null}
          </div>
        ))}
      </div>
    </section>
  );
}
