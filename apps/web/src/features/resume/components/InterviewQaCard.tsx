"use client";

/**
 * @file InterviewQaCard.tsx
 * @description One predicted interview question as a drill card: intent, answer points, follow-ups.
 *
 * Shared by the interview-drill tab and the project deep-dive cards. Tolerates
 * rows persisted before the structured shape (missing list fields).
 */

import { HelpCircle } from "lucide-react";
import type { InterviewQa } from "../types";
import { normalizeCnPunctuation } from "@/lib/cnText";
import { useT } from "@/i18n";
import { EvalRichText } from "./EvalRichText";

export function InterviewQaCard({ item, index }: { item: InterviewQa; index: number }) {
  const t = useT("resume");
  const cn = normalizeCnPunctuation;
  const points = item.answer_points ?? [];
  const followUps = item.follow_ups ?? [];
  return (
    <div className="eval-qa-card">
      <div className="mb-1.5 flex items-start gap-2">
        <span className="eval-qa-idx num-tabular">{index + 1}</span>
        <p className="min-w-0 text-[13px] font-semibold leading-snug text-ink">
          <EvalRichText text={cn(item.question ?? "")} />
        </p>
      </div>
      {item.intent?.trim() ? (
        <p className="eval-qa-row text-[12px] leading-relaxed text-ink-muted">
          <span className="mr-1 shrink-0 font-medium text-ink-subtle">
            {t("interview.qaIntent")}:
          </span>
          <EvalRichText text={cn(item.intent)} />
        </p>
      ) : null}
      {points.length > 0 && (
        <div className="eval-qa-row">
          <p className="eval-qa-sublabel">{t("interview.qaPoints")}</p>
          <ul className="eval-list eval-list-tight">
            {points.map((point, j) => (
              <li key={j}>
                <span className="eval-list-mark">·</span>
                <span className="eval-list-body">
                  <EvalRichText text={cn(point)} />
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {followUps.length > 0 && (
        <div className="eval-qa-row">
          <p className="eval-qa-sublabel">
            <HelpCircle size={11} />
            {t("interview.qaFollowUps")}
          </p>
          <ul className="eval-list eval-list-tight">
            {followUps.map((q, j) => (
              <li key={j}>
                <span className="eval-list-mark">·</span>
                <span className="eval-list-body text-ink-muted">
                  <EvalRichText text={cn(q)} />
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
