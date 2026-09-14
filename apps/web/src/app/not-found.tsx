"use client";

import Link from "next/link";
import { Compass, Home } from "lucide-react";
import { useT } from "@/i18n";

export default function NotFound() {
  const t = useT("common");
  return (
    <main className="flex min-h-[70vh] flex-col items-center justify-center px-6 text-center">
      <span className="empty-state-icon">
        <Compass size={24} />
      </span>
      <p className="page-eyebrow mt-4">404</p>
      <h1 className="mt-1 text-[22px] font-semibold tracking-tight text-ink">{t("nf.title")}</h1>
      <p className="mt-2 max-w-md text-[13px] leading-relaxed text-ink-muted">
        {t("nf.description")}
      </p>
      <Link href="/" className="btn-primary mt-7">
        <Home size={14} /> {t("action.backHome")}
      </Link>
    </main>
  );
}
