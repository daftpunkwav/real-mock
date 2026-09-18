"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowRight } from "lucide-react";

/**
 * The primary call-to-action, sized for the hero. Same voice as the app's
 * .btn-primary (profile's save button): solid brand fill with a soft vertical
 * roll-off, a hairline top highlight and a subtle bottom shade for volume.
 * Shared by the hero and the closing section so the page has one CTA voice.
 */
export function StageButton({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="group inline-flex h-[52px] items-center justify-center gap-2 rounded-xl px-8 text-[16px] font-medium text-white transition-[transform,filter,box-shadow] duration-200 hover:-translate-y-px hover:brightness-110 active:translate-y-0 active:scale-[0.99]"
      style={{
        background:
          "linear-gradient(180deg, color-mix(in srgb, var(--primary) 86%, white) 0%, var(--primary) 42%, color-mix(in srgb, var(--primary) 88%, black) 100%)",
        boxShadow:
          "var(--shadow-brand), 0 4px 14px -6px rgba(66,133,244,0.35), inset 0 1px 0 rgba(255,255,255,0.28), inset 0 -1px 0 rgba(0,0,0,0.16)",
      }}
    >
      {children}
      <ArrowRight size={16} className="transition-transform duration-200 group-hover:translate-x-0.5" />
    </Link>
  );
}
