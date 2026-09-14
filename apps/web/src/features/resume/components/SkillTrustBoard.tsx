"use client";

/**
 * @file SkillTrustBoard.tsx
 * @description Three-column skill trust board (solid / claimed / missing).
 *
 * Column keys come from resumeLimits.TRUST_KEYS; copy lives in i18n.
 */

import { ShieldCheck, ShieldQuestion, Sparkles } from "lucide-react";
import { useT, type MessageKey } from "@/i18n";
import type { SkillTrustData } from "../types";
import { TRUST_KEYS, type TrustKey } from "../resumeLimits";

/* ── ─────────────────────────────── */

const TRUST_ICONS: Record<TrustKey, React.ReactNode> = {
  solid: <ShieldCheck size={13} />,
  claimed: <ShieldQuestion size={13} />,
  missing: <Sparkles size={13} />,
};

const TRUST_COLS: Array<{
  key: TrustKey;
  titleKey: MessageKey<"resume">;
  hintKey: MessageKey<"resume">;
  cls: string;
}> = TRUST_KEYS.map((key) => ({
  key,
  titleKey: `trust.${key}.title` as MessageKey<"resume">,
  hintKey: `trust.${key}.hint` as MessageKey<"resume">,
  cls: `is-${key}`,
}));

export function SkillTrustBoard({ trust }: { trust: SkillTrustData }) {
  const t = useT("resume");
  const filled = TRUST_COLS.filter((c) => (trust[c.key]?.length ?? 0) > 0);
  if (filled.length === 0) return null;

  return (
    <section className="eval-section">
      <span className="eval-label">{t("advice.trustBoard")}</span>
      <div className="eval-trust-grid">
        {filled.map((col) => {
          const items = trust[col.key] ?? [];
          return (
            <div key={col.key} className={`eval-trust-col ${col.cls}`}>
              <p className="eval-trust-title">
                {TRUST_ICONS[col.key]}
                {t(col.titleKey)}
                <span className="eval-trust-count num-tabular">{items.length}</span>
              </p>
              <p className="eval-trust-hint">{t(col.hintKey)}</p>
              <div className="eval-trust-chips">
                {items.map((s, i) => (
                  <span key={i} className="eval-trust-chip">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
