"use client";

/**
 * @file EvalList.tsx
 * @description Bulleted evaluation list with sanitized rich text.
 */

import { EvalRichText } from "./EvalRichText";

export function EvalList({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="eval-section min-w-0">
      <span className="eval-label">{title}</span>
      <ul className="eval-list">
        {items.map((s, i) => (
          <li key={i}>
            <span className="eval-list-mark">·</span>
            <span className="eval-list-body">
              <EvalRichText text={s} />
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
