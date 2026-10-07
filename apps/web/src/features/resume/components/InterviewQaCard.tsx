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
import { SendToPrepButton } from "./SendToPrepButton";

/** Bulleted subsection of a drill card (answer points or follow-ups). */
const QaBulletList = ({
  items,
  label,
  icon,
  muted,
}: {
  items: string[];
  label: string;
  icon?: React.ReactNode;
  muted?: boolean;
}) => {
  const cn = normalizeCnPunctuation;
  return (
    <div className="eval-qa-row">
      <p className="eval-qa-sublabel">
        {icon}
        {label}
      </p>
      <ul className="eval-list eval-list-tight">
        {items.map((item, j) => (
          <li key={j}>
            <span className="eval-list-mark">·</span>
            <span className={muted ? "eval-list-body text-ink-muted" : "eval-list-body"}>
              <EvalRichText text={cn(item)} />
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
};

export const InterviewQaCard = ({
  item,
  index,
  resumeId,
}: {
  item: InterviewQa;
  index: number;
  /** Owning resume id; pairs the seeded prep session with the same resume. */
  resumeId?: number | null;
}) => {
  const t = useT("resume");
  const cn = normalizeCnPunctuation;
  const points = item.answer_points ?? [];
  const followUps = item.follow_ups ?? [];
  const question = cn(item.question ?? "");
  return (
    <div className="eval-qa-card">
      <div className="mb-1.5 flex items-start gap-2">
        <span className="eval-qa-idx num-tabular">{index + 1}</span>
        <p className="min-w-0 flex-1 text-[13px] font-semibold leading-snug text-ink">
          <EvalRichText text={question} />
        </p>
        {question.trim() ? (
          <SendToPrepButton question={question} resumeId={resumeId ?? null} />
        ) : null}
      </div>
      {item.intent?.trim() ? (
        <p className="eval-qa-row text-[12px] leading-relaxed text-ink-muted">
          <span className="mr-1 shrink-0 font-medium text-ink-subtle">
            {t("interview.qaIntent")}:
          </span>
          <EvalRichText text={cn(item.intent)} />
        </p>
      ) : null}
      {points.length > 0 && <QaBulletList items={points} label={t("interview.qaPoints")} />}
      {followUps.length > 0 && (
        <QaBulletList
          items={followUps}
          label={t("interview.qaFollowUps")}
          icon={<HelpCircle size={11} />}
          muted
        />
      )}
    </div>
  );
};
