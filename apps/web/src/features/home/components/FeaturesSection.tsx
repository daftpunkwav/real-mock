"use client";

import { motion, useReducedMotion } from "framer-motion";
import { ArrowUpRight } from "lucide-react";
import { useT } from "@/i18n";
import { FEATURES } from "../content";
import { TintIcon } from "./TintIcon";

export function FeaturesSection() {
  const reduce = useReducedMotion();
  const t = useT("home");

  return (
    <section className="relative mx-auto max-w-[1200px] px-5 sm:px-6 lg:px-8 pt-20 sm:pt-28">
      <div className="mx-auto max-w-[62ch] text-center">
        <p className="page-eyebrow">{t("features.eyebrow")}</p>
        <h2 className="page-title">{t("features.title")}</h2>
        <p className="page-desc mx-auto">{t("features.desc")}</p>
      </div>

      <div className="mt-10 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 lg:gap-4">
        {FEATURES.map((f, i) => (
          <motion.div
            key={f.titleKey}
            initial={reduce ? false : { opacity: 0, y: 14 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.5, delay: (i % 3) * 0.07, ease: [0.16, 1, 0.3, 1] }}
            className="glass-card group h-full p-5"
          >
            <div className="mb-4 flex items-center justify-between">
              <TintIcon icon={f.icon} tint={f.tint} />
              <ArrowUpRight
                size={14}
                className="text-ink-subtle opacity-0 transition-all group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:opacity-100 group-hover:text-brand"
              />
            </div>
            <h3 className="mb-1 text-[14px] font-semibold text-ink">{t(f.titleKey)}</h3>
            <p className="text-[13px] leading-relaxed text-ink-muted">{t(f.descKey)}</p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
