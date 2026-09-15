"use client";

/**
 * External verification notes surfaced by the report synthesis agent.
 * Pure display component: receives pre-rendered note strings from the report page.
 */

import { Fragment } from "react";
import { Globe } from "lucide-react";
import { useT } from "@/i18n";

const URL_RE = /(https?:\/\/[^\s)>\]]+)/g;
/** Trailing sentence punctuation is prose, not part of the URL. */
const TRAILING_PUNCT_RE = /([。、，；：？！,.!?;:)\]}>]+)$/;

/** Render note text with source URLs as clickable links. */
function LinkifiedNote({ text }: { text: string }) {
  // Only http(s) URLs linkify, so non-navigating schemes can never execute.
  const parts = text.split(URL_RE);
  return (
    <span className="min-w-0 break-words">
      {parts.map((part, i) => {
        if (i % 2 === 0) return <Fragment key={i}>{part}</Fragment>;
        const punct = part.match(TRAILING_PUNCT_RE)?.[1] ?? "";
        const href = punct ? part.slice(0, -punct.length) : part;
        if (!href) return <Fragment key={i}>{part}</Fragment>;
        return (
          <Fragment key={i}>
            <a
              href={href}
              target="_blank"
              rel="noreferrer noopener"
              className="break-all underline underline-offset-2 hover:opacity-80"
            >
              {href}
            </a>
            {punct || null}
          </Fragment>
        );
      })}
    </span>
  );
}

/** External verification notes the report agent grounded via web tools. */
export function ExternalNotesCard({ notes }: { notes?: string[] }) {
  const t = useT("report");
  if (!notes?.length) return null;
  return (
    <div
      className="mt-4 rounded-md border p-4"
      style={{
        background: "var(--info-soft)",
        borderColor: "color-mix(in srgb, var(--primary) 22%, transparent)",
      }}
    >
      <h3
        className="mb-2 flex items-center gap-1.5 text-[12px] font-semibold uppercase tracking-[0.08em]"
        style={{ color: "var(--info-ink)" }}
      >
        <Globe size={12} />
        {t("sections.externalNotes")}
      </h3>
      <ul className="space-y-1.5">
        {notes.map((note, i) => (
          <li key={i} className="flex items-start gap-2 text-[13px] leading-relaxed text-ink">
            <span className="mt-1 inline-block h-1 w-1 shrink-0 rounded-full bg-current opacity-50" />
            <LinkifiedNote text={note} />
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[11px]" style={{ color: "var(--info-ink)" }}>
        {t("externalNotes.hint")}
      </p>
    </div>
  );
}
