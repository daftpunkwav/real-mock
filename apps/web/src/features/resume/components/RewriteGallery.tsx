"use client";

/**
 * @file RewriteGallery.tsx
 * @description Before/after rewrite examples for resume bullets.
 */

import type { ResumeAnalysis } from "../types";
import { normalizeCnPunctuation, parseRewriteExample } from "@/lib/cnText";
import { useT } from "@/i18n";
import { EvalRichText } from "./EvalRichText";
import { EvalList } from "./EvalList";

export function RewriteGallery({
  items,
}: {
  items: NonNullable<ResumeAnalysis["rewrite_examples"]>;
}) {
  const t = useT("resume");
  const pairs = items
    .map((item) => parseRewriteExample(item))
    .filter((p): p is { before: string; after: string } => Boolean(p));

  if (pairs.length === 0) {
    // Fallback: no parseable before/after pairs, render raw items as a list.
    const fallback = items
      .map((item) => {
        if (typeof item === "string") return normalizeCnPunctuation(item);
        if (item && typeof item === "object") {
          const b = "before" in item ? String(item.before || "") : "";
          const a = "after" in item ? String(item.after || "") : "";
          if (b && a) return null;
          return normalizeCnPunctuation(JSON.stringify(item));
        }
        return null;
      })
      .filter((x): x is string => Boolean(x));
    if (!fallback.length) return null;
    return <EvalList title={t("rewrite.title")} items={fallback} />;
  }

  return (
    <section className="eval-section">
      <span className="eval-label">{t("rewrite.title")}</span>
      <div className="eval-rewrite-stack">
        {pairs.map((pair, i) => (
          <article key={i} className="eval-rewrite-card">
            <div className="eval-rewrite-block is-before">
              <div className="eval-rewrite-meta">
                <span className="eval-rewrite-idx">{String(i + 1).padStart(2, "0")}</span>
                <span className="eval-rewrite-tag">{t("rewrite.before")}</span>
              </div>
              <p className="eval-rewrite-text">
                <EvalRichText text={normalizeCnPunctuation(pair.before)} />
              </p>
            </div>
            <div className="eval-rewrite-block is-after">
              <div className="eval-rewrite-meta">
                <span className="eval-rewrite-tag">{t("rewrite.after")}</span>
              </div>
              <p className="eval-rewrite-text">
                <EvalRichText text={normalizeCnPunctuation(pair.after)} />
              </p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
