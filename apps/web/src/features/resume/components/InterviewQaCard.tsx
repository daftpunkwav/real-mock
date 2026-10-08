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

/** Card header: numbered question with its send-to-prep action. */
const QaCardHeader = ({
  index,
  question,
  resumeId,
}: {
  index: number;
  question: string;
  resumeId: number | null;
}) => (
  <div className="mb-1.5 flex items-start gap-2">
    <span className="eval-qa-idx num-tabular">{index + 1}</span>
    <p className="min-w-0 flex-1 text-[13px] font-semibold leading-snug text-ink">
      <EvalRichText text={question} />
    </p>
    {question.trim() ? <SendToPrepButton question={question} resumeId={resumeId} /> : null}
  </div>
);

/** The interviewer-intent line under the question (nothing renders without one). */
const QaIntentLine = ({ intent }: { intent?: string }) => {
  const t = useT("resume");
  if (!intent?.trim()) return null;
  return (
    <p className="eval-qa-row text-[12px] leading-relaxed text-ink-muted">
      <span className="mr-1 shrink-0 font-medium text-ink-subtle">{t("interview.qaIntent")}:</span>
      <EvalRichText text={normalizeCnPunctuation(intent)} />
    </p>
  );
};

/** Optional bullet section that renders only when the list has items. */
const QaOptionalList = ({
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
  if (items.length === 0) return null;
  return <QaBulletList items={items} label={label} icon={icon} muted={muted} />;
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
  const points = item.answer_points ?? [];
  const followUps = item.follow_ups ?? [];
  const question = normalizeCnPunctuation(item.question ?? "");
  return (
    <div className="eval-qa-card">
      <QaCardHeader index={index} question={question} resumeId={resumeId ?? null} />
      <QaIntentLine intent={item.intent} />
      <QaOptionalList items={points} label={t("interview.qaPoints")} />
      <QaOptionalList
        items={followUps}
        label={t("interview.qaFollowUps")}
        icon={<HelpCircle size={11} />}
        muted
      />
    </div>
  );
};
