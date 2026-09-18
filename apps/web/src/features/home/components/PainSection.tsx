"use client";

import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { useT } from "@/i18n";
import { PAIN_POINTS } from "../content";

/** Why mock interviews usually fail — three failure modes, each with the answer. */
export function PainSection() {
  const t = useT("home");
  const reduce = useReducedMotion();

  return (
    <section className="relative mx-auto max-w-[1200px] px-5 sm:px-6 lg:px-8 pt-20 sm:pt-28">
      <div className="mx-auto max-w-[62ch] text-center">
        <p className="page-eyebrow">{t("pain.eyebrow")}</p>
        <h2 className="page-title">{t("pain.title")}</h2>
        <p className="page-desc mx-auto">{t("pain.desc")}</p>
      </div>

      <div className="mt-10 grid grid-cols-1 gap-4 md:grid-cols-3">
        {PAIN_POINTS.map(({ icon: Icon, titleKey, descKey, featureKey }, i) => (
          <motion.div
            key={titleKey}
            initial={reduce ? false : { opacity: 0, y: 14 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.5, delay: i * 0.07, ease: [0.16, 1, 0.3, 1] }}
            className="glass-card p-5"
          >
            <span className="icon-badge icon-badge-danger !h-8 !w-8">
              <Icon size={15} strokeWidth={1.75} />
            </span>
            <h3 className="mt-3 text-[15px] font-semibold text-ink">{t(titleKey)}</h3>
            <p className="mt-1.5 text-[13px] leading-relaxed text-ink-muted">{t(descKey)}</p>
            <p className="mt-3.5 flex items-center gap-1.5 border-t border-surface-border pt-3 text-[12px] font-medium text-[var(--primary)]">
              <ArrowRight size={12} className="shrink-0" />
              {t(featureKey)}
            </p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
