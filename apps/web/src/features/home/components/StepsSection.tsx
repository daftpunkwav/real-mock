"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { useT } from "@/i18n";
import { STEPS } from "../content";
import { FlowItem, useFlowProgress } from "./ScrollFlow";

export function StepsSection() {
  const prefersReduce = useReducedMotion();
  const t = useT("home");
  const { ref, progress, reduce } = useFlowProgress<HTMLElement>();

  return (
    <section
      ref={ref}
      className="relative mx-auto max-w-[1200px] px-5 sm:px-6 lg:px-8 pt-20 sm:pt-28"
    >
      <FlowItem progress={progress} reduce={reduce} className="mx-auto max-w-[62ch] text-center">
        <p className="page-eyebrow">{t("steps.eyebrow")}</p>
        <h2 className="page-title sm:!text-[30px]">{t("steps.title")}</h2>
        <p className="page-desc mx-auto">{t("steps.desc")}</p>
      </FlowItem>

      <div className="relative mt-10 grid grid-cols-1 gap-3 md:grid-cols-3 md:gap-4">
        {/* Connector line draws itself left→right when the row enters view */}
        {!prefersReduce && (
          <motion.span
            aria-hidden
            initial={{ scaleX: 0 }}
            whileInView={{ scaleX: 1 }}
            viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.9, delay: 0.2, ease: [0.77, 0, 0.175, 1] }}
            className="pointer-events-none absolute left-[16%] right-[16%] top-9 hidden h-px origin-left bg-gradient-to-r from-[color-mix(in_srgb,var(--primary)_60%,transparent)] to-[color-mix(in_srgb,var(--primary)_12%,transparent)] md:block"
          />
        )}
        {STEPS.map((step, i) => (
          <FlowItem key={step.n} progress={progress} reduce={reduce} index={i + 1}>
            <Link
              href={step.href}
              className="stage-card group relative flex h-full flex-col p-5 sm:p-6"
            >
              <div className="mb-5 flex items-start justify-between">
                <span className="font-mono text-xs font-semibold tracking-wide text-brand">
                  {step.n}
                </span>
                <span className="icon-badge icon-badge-muted group-hover:icon-badge-brand transition-colors">
                  <step.icon size={15} strokeWidth={1.75} />
                </span>
              </div>
              <h3 className="mb-1.5 text-[15px] font-semibold text-ink">{t(step.titleKey)}</h3>
              <p className="flex-1 text-[13px] leading-relaxed text-ink-muted">{t(step.descKey)}</p>
              <div className="mt-5 flex items-center gap-1 text-[12px] font-medium text-brand">
                <span>{t("steps.go")}</span>
                <ArrowRight size={12} className="btn-arrow transition-transform" />
              </div>
              {i < STEPS.length - 1 && (
                <span
                  className="pointer-events-none absolute right-[-10px] top-1/2 hidden h-5 w-5 -translate-y-1/2 items-center justify-center rounded-full border border-surface-border bg-surface-card text-ink-subtle md:flex"
                  aria-hidden
                >
                  <ArrowRight size={10} />
                </span>
              )}
            </Link>
          </FlowItem>
        ))}
      </div>
    </section>
  );
}
