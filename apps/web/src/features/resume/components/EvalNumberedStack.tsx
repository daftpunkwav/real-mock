"use client";

/**
 * @file EvalNumberedStack.tsx
 * @description Numbered stack of evaluation items (P1 / Q1 prefixes).
 */

import { EvalRichText } from "./EvalRichText";

export function EvalNumberedStack({
  title,
  items,
  prefix,
}: {
  title: string;
  items: string[];
  prefix: string;
}) {
  return (
    <section className="eval-section">
      <span className="eval-label">{title}</span>
      <div className="eval-q-stack">
        {items.map((q, i) => (
          <div key={i} className="eval-q">
            <span className="eval-q-idx">
              {prefix}
              {i + 1}
            </span>
            <p className="eval-prose eval-prose-sm !max-w-none m-0">
              <EvalRichText text={q} />
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
