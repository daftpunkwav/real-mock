"use client";

/**
 * @file ProjectCards.tsx
 * @description Expandable project deep-dive cards with must-ask interview drill questions.
 */

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { BadgeCheck, ChevronDown, CircleAlert, CircleHelp } from "lucide-react";
import type { ProjectCardData } from "../types";
import { withContentKeys } from "../contentKey";
import { normalizeCnPunctuation } from "@/lib/cnText";
import { useT } from "@/i18n";
import { EvalRichText } from "./EvalRichText";
import { InterviewQaCard } from "./InterviewQaCard";
import { SendToPrepButton } from "./SendToPrepButton";
import { scoreColor } from "@/lib/scoreColor";

/** Plain-string deep-dive question with a "send to prep" action. */
function DeepDiveQuestionRow({
  question,
  resumeId,
}: {
  question: string;
  resumeId?: number | null;
}) {
  if (!question.trim()) return null;
  return (
    <div className="flex items-start gap-2">
      <p className="eval-pcard-q min-w-0 flex-1">
        <EvalRichText text={question} />
      </p>
      <SendToPrepButton question={question} resumeId={resumeId ?? null} />
    </div>
  );
}

/** Shared layout for a labelled card section (highlights or risks). */
function CardListSection({
  label,
  icon,
  labelClass,
  items,
}: {
  label: string;
  icon: React.ReactNode;
  labelClass: string;
  items: string[];
}) {
  if (items.length === 0) return null;
  const cn = normalizeCnPunctuation;
  return (
    <div className="eval-pcard-col">
      <p className={`eval-pcard-label ${labelClass}`}>
        {icon} {label}
      </p>
      <ul className="eval-pcard-list">
        {withContentKeys(items, (item) => cn(item)).map(({ item, key }) => (
          <li key={key}>
            <EvalRichText text={cn(item)} />
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Must-ask drill questions: plain strings get a send-to-prep row, structured
 * rows render as full interview QA cards. */
function CardDeepQuestions({
  questions,
  resumeId,
}: {
  questions: NonNullable<ProjectCardData["deep_questions"]>;
  resumeId?: number | null;
}) {
  const t = useT("resume");
  if (questions.length === 0) return null;
  const cn = normalizeCnPunctuation;
  return (
    <div className="eval-pcard-questions">
      <p className="eval-pcard-label text-[var(--primary-ink)]">
        <CircleHelp size={12} /> {t("projects.mustAsk")}
      </p>
      <div className="eval-pcard-qwrap">
        {withContentKeys(questions, (q) => (typeof q === "string" ? q : (q.question ?? ""))).map(
          ({ item: q, key }, i) =>
            typeof q === "string" ? (
              <DeepDiveQuestionRow key={key} question={cn(q)} resumeId={resumeId} />
            ) : (
              <InterviewQaCard key={key} item={q} index={i} resumeId={resumeId} />
            ),
        )}
      </div>
    </div>
  );
}

/** One expandable card; the first card starts open. */
function ProjectCardItem({
  card,
  index,
  resumeId,
}: {
  card: ProjectCardData;
  index: number;
  resumeId?: number | null;
}) {
  const t = useT("resume");
  const cn = normalizeCnPunctuation;
  const [open, setOpen] = useState(index === 0);
  const color = scoreColor(card.score);
  const highlights = card.highlights ?? [];
  const risks = card.risks ?? [];
  const deepQuestions = card.deep_questions ?? [];

  return (
    <div className={`eval-pcard ${open ? "is-open" : ""}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="eval-pcard-head"
        aria-expanded={open}
      >
        <span className="eval-pcard-idx num-tabular">{String(index + 1).padStart(2, "0")}</span>
        <span className="min-w-0 flex-1 text-left">
          <span className="eval-pcard-name">{card.name}</span>
          <span className="eval-pcard-line">{cn(card.one_line)}</span>
        </span>
        <span className="eval-pcard-score num-tabular" style={{ color }}>
          {card.score}
          <span
            className="eval-pcard-score-ring"
            style={{ background: `conic-gradient(${color} ${card.score}%, var(--muted) 0)` }}
            aria-hidden
          />
        </span>
        <ChevronDown
          size={15}
          className={`shrink-0 text-ink-subtle transition-transform duration-300 ${open ? "rotate-180" : ""}`}
        />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="eval-pcard-body">
              <CardListSection
                label={t("projects.highlight")}
                icon={<BadgeCheck size={12} />}
                labelClass="text-[var(--success)]"
                items={highlights}
              />
              <CardListSection
                label={t("projects.risk")}
                icon={<CircleAlert size={12} />}
                labelClass="text-[var(--warning-ink)]"
                items={risks}
              />
              <CardDeepQuestions questions={deepQuestions} resumeId={resumeId} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function ProjectCards({
  cards,
  resumeId,
}: {
  cards: ProjectCardData[];
  resumeId?: number | null;
}) {
  const t = useT("resume");
  const cleaned = cards.filter((c) => c.name);
  if (cleaned.length === 0) return null;
  return (
    <section className="eval-section">
      <span className="eval-label">{t("projects.cardsTitle")}</span>
      <div className="eval-pcard-stack">
        {withContentKeys(cleaned, (c) => c.name).map(({ item: c, key }, i) => (
          <ProjectCardItem key={key} card={c} index={i} resumeId={resumeId} />
        ))}
      </div>
    </section>
  );
}
