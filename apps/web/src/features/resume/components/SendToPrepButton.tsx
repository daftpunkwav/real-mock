"use client";

/**
 * @file SendToPrepButton.tsx
 * @description Per-question "send to prep" action shared by the deep-review
 * tabs: deep-links into /prep with the templated question pre-sent, carrying
 * the owning resume id for session pairing.
 */

import { SendHorizontal } from "lucide-react";
import { useRouter } from "next/navigation";
import { useT } from "@/i18n";
import { buildPrepDeepLink } from "../sendToPrep";

export function SendToPrepButton({
  question,
  resumeId,
}: {
  /** Raw question text; templated into the seeded prep message as-is. */
  question: string;
  /** Owning resume id; pairs the seeded prep session with the same resume. */
  resumeId: number | null;
}) {
  const t = useT("resume");
  const router = useRouter();
  return (
    <button
      type="button"
      onClick={() => {
        router.push(buildPrepDeepLink(resumeId, t("sendToPrep.template", { question })));
      }}
      title={t("sendToPrep.action")}
      aria-label={t("sendToPrep.action")}
      className="shrink-0 self-center rounded-md border border-surface-border p-1.5 text-ink-subtle transition-colors hover:border-[var(--primary)] hover:text-[var(--primary)]"
    >
      <SendHorizontal size={12} />
    </button>
  );
}
