"use client";

/**
 * @file SectionHeatmap.tsx
 * @description Per-section score heatmap with expandable detail.
 */

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { MapPin } from "lucide-react";
import type { SectionReview } from "../types";
import { normalizeCnPunctuation } from "@/lib/cnText";
import { useT } from "@/i18n";
import { EvalRichText } from "./EvalRichText";
import { scoreColor } from "@/lib/scoreColor";

/** Segmented score heatmap; the active segment expands its detail below. */
export function SectionHeatmap({ reviews }: { reviews: SectionReview[] }) {
  const t = useT("resume");
  const cn = normalizeCnPunctuation;
  const cleaned = reviews.filter((r) => r.section && r.score > 0);
  const [active, setActive] = useState(0);
  if (cleaned.length === 0) return null;
  const current = cleaned[Math.min(active, cleaned.length - 1)]!;

  return (
    <section className="eval-section">
      <span className="eval-label">{t("document.heatTitle")}</span>
      <div className="eval-heat" role="tablist" aria-label={t("document.heatAria")}>
        {cleaned.map((r, i) => (
          <button
            key={`${r.section}-${i}`}
            type="button"
            role="tab"
            aria-selected={i === active}
            onClick={() => setActive(i)}
            className={`eval-heat-seg ${i === active ? "is-active" : ""}`}
            style={{
              flexGrow: Math.max(r.detail.length, 40),
              "--seg-color": scoreColor(r.score),
            } as React.CSSProperties}
          >
            <span className="eval-heat-score num-tabular">{r.score}</span>
            <span className="eval-heat-name">{r.section}</span>
          </button>
        ))}
      </div>
      <AnimatePresence mode="wait">
        <motion.div
          key={current.section}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.22 }}
          className="eval-heat-detail"
        >
          <p className="eval-heat-verdict">
            <MapPin size={13} className="shrink-0 text-[var(--primary)]" />
            {cn(current.verdict)}
          </p>
          <p className="eval-heat-body">
            <EvalRichText text={cn(current.detail)} />
          </p>
        </motion.div>
      </AnimatePresence>
    </section>
  );
}
