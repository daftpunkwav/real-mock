"use client";

/**
 * @file EvalRichText.tsx
 * @description Tokenize **bold** / `code` spans in evaluation copy.
 */

import { tokenizeEvalText } from "@/lib/cnText";
import type { EvalTextPart } from "@/lib/cnText";

/** Render bold and code spans from tokenized text. */
export function EvalRichText({ text }: { text: string }) {
  const parts = tokenizeEvalText(text);
  return (
    <>
      {parts.map((p, i) => (
        <EvalRichPart key={i} part={p} />
      ))}
    </>
  );
}

function EvalRichPart({ part }: { part: EvalTextPart }) {
  if (part.type === "bold") {
    return <strong className="eval-em">{part.value}</strong>;
  }
  if (part.type === "code") {
    return <code className="eval-code">{part.value}</code>;
  }
  return <>{part.value}</>;
}
