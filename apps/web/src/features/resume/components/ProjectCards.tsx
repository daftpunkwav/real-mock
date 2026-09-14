"use client";

/**
 * @file ProjectCards.tsx
 * @description Expandable project deep-dive cards with must-ask interview drill questions.
 */

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { BadgeCheck, ChevronDown, CircleAlert, CircleHelp } from "lucide-react";
import type { ProjectCardData } from "../types";
import { normalizeCnPunctuation } from "@/lib/cnText";
import { useT } from "@/i18n";
import { EvalRichText } from "./EvalRichText";
import { InterviewQaCard } from "./InterviewQaCard";
import { scoreColor } from "@/lib/scoreColor";

/** One expandable card; the first card starts open. */
function ProjectCardItem({ card, index }: { card: ProjectCardData; index: number }) {
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
          <span className="eval-pcard-score-ring" style={{ background: `conic-gradient(${color} ${card.score}%, var(--muted) 0)` }} aria-hidden />
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
              {highlights.length > 0 && (
                <div className="eval-pcard-col">
                  <p className="eval-pcard-label text-[var(--success)]">
                    <BadgeCheck size={12} /> {t("projects.highlight")}
                  </p>
                  <ul className="eval-pcard-list">
                    {highlights.map((h, i) => (
                      <li key={i}>
                        <EvalRichText text={cn(h)} />
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {risks.length > 0 && (
                <div className="eval-pcard-col">
                  <p className="eval-pcard-label text-[var(--warning-ink)]">
                    <CircleAlert size={12} /> {t("projects.risk")}
                  </p>
                  <ul className="eval-pcard-list">
                    {risks.map((r, i) => (
                      <li key={i}>
                        <EvalRichText text={cn(r)} />
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {deepQuestions.length > 0 && (
                <div className="eval-pcard-questions">
                  <p className="eval-pcard-label text-[var(--primary-ink)]">
                    <CircleHelp size={12} /> {t("projects.mustAsk")}
                  </p>
                  <div className="eval-pcard-qwrap">
                    {deepQuestions.map((q, i) =>
                      typeof q === "string" ? (
                        <p key={i} className="eval-pcard-q">
                          <EvalRichText text={cn(q)} />
                        </p>
                      ) : (
                        <InterviewQaCard key={i} item={q} index={i} />
                      ),
                    )}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function ProjectCards({ cards }: { cards: ProjectCardData[] }) {
  const t = useT("resume");
  const cleaned = cards.filter((c) => c.name);
  if (cleaned.length === 0) return null;
  return (
    <section className="eval-section">
      <span className="eval-label">{t("projects.cardsTitle")}</span>
      <div className="eval-pcard-stack">
        {cleaned.map((c, i) => (
          <ProjectCardItem key={`${c.name}-${i}`} card={c} index={i} />
        ))}
      </div>
    </section>
  );
}
