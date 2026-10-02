"use client";

/**
 * @file AskViewCard.tsx
 * @description Read-only replay of an ask_user dialog inside the conversation:
 * the questions and options the coach asked, viewable after the live modal is
 * gone or the user has already answered. Pure display — no submit channel.
 */

import { memo, useState } from "react";
import { ChevronRight, HelpCircle, Star } from "lucide-react";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";
import type { AskUserDialog } from "@/types";

/** Questions to replay: the multi array when present, else the flat single. */
function questionsOf(ask: AskUserDialog): AskUserDialog[] {
  return ask.questions && ask.questions.length > 0 ? ask.questions : [ask];
}

export const AskViewCard = memo(function AskViewCard({ ask }: { ask: AskUserDialog }) {
  const t = useT("prep");
  const [open, setOpen] = useState(false);
  const questions = questionsOf(ask);

  return (
    <div className="overflow-hidden rounded-md border border-surface-border bg-surface-alt">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[11px] text-ink-muted transition-colors hover:bg-surface-muted"
      >
        <ChevronRight
          size={13}
          className={cn("shrink-0 text-ink-subtle transition-transform", open && "rotate-90")}
        />
        <HelpCircle size={12} className="shrink-0 text-[var(--primary)]" />
        <span className="font-medium">{t("chat.viewAsk")}</span>
        {!open && (
          <span className="min-w-0 flex-1 truncate text-ink-subtle">
            {questions.map((q) => q.question).join(" / ")}
          </span>
        )}
      </button>
      {open && (
        <div className="space-y-3 border-t border-surface-border px-3 py-2.5">
          {questions.map((q, idx) => (
            <div key={idx} className="space-y-1.5">
              <p className="text-[12px] font-medium leading-relaxed text-ink">
                <span className="mr-1.5 text-ink-subtle">{idx + 1}.</span>
                {q.question}
              </p>
              {q.widget === "slider" && (
                <p className="text-[11px] text-ink-subtle">
                  {q.scale?.min ?? 0} – {q.scale?.max ?? 10}
                  {q.scale?.unit ? ` ${q.scale.unit}` : ""}
                </p>
              )}
              {q.widget === "rating" && (
                <p className="flex items-center gap-1 text-[11px] text-ink-subtle">
                  {Array.from(
                    { length: Math.min(10, Math.max(3, Math.round(q.scale?.max ?? 5))) },
                    (_, i) => (
                      <Star key={i} size={12} className="text-ink-subtle" />
                    ),
                  )}
                </p>
              )}
              {q.widget === "options" && (
                <div className="space-y-1">
                  {q.options.map((opt) => (
                    <div
                      key={opt}
                      className="flex w-full items-center gap-2 rounded-md border border-surface-border bg-surface-alt px-2.5 py-1.5 text-left text-[12px] text-ink-muted"
                    >
                      <span
                        className={cn(
                          "shrink-0 rounded-full border border-ink-subtle",
                          q.selection === "multi"
                            ? "h-[12px] w-[12px] rounded-[3px]"
                            : "h-[12px] w-[12px]",
                        )}
                      />
                      <span className="min-w-0 flex-1">{opt}</span>
                      {q.suggested === opt && (
                        <span className="ml-auto shrink-0 rounded-full bg-[var(--primary)] px-2 py-0.5 text-[10px] font-medium text-white">
                          {t("ask.recommended")}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
});
