"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { useT } from "@/i18n";

export function CtaSection() {
  const t = useT("home");

  return (
    <section className="bg-surface">
      <div className="mx-auto max-w-[1320px] px-5 sm:px-6 lg:px-10 py-14 sm:py-16">
        <div className="relative overflow-hidden rounded-lg border border-surface-border bg-surface-card p-7 sm:p-10">
          <div
            className="pointer-events-none absolute inset-0 opacity-90"
            style={{
              background:
                "radial-gradient(640px 260px at 90% 0%, color-mix(in srgb, var(--primary) 16%, transparent), transparent 55%), radial-gradient(420px 200px at 8% 100%, color-mix(in srgb, var(--chart-5) 14%, transparent), transparent 50%)",
            }}
            aria-hidden
          />
          <div className="relative flex flex-col items-start justify-between gap-6 sm:flex-row sm:items-center">
            <div>
              <h2 className="text-[20px] sm:text-[24px] font-semibold leading-tight tracking-tight text-ink">
                {t("cta.title")}
              </h2>
              <p className="mt-2 text-[13px] text-ink-muted">
                {t("cta.desc")}
              </p>
            </div>
            <Link
              href="/interview"
              className="btn-primary"
            >
              {t("cta.action")}
              <ArrowRight size={14} className="btn-arrow transition-transform" />
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
