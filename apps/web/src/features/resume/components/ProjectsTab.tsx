"use client";

/**
 * @file ProjectsTab.tsx
 * @description Project deep-dive: repo evidence, claim verdicts, project cards, deep-dive points.
 */

import { ExternalLink, Github, Star } from "lucide-react";
import type { ResumeAnalysis, RepoEvidence, RepoVerification } from "../types";
import { normalizeCnPunctuation } from "@/lib/cnText";
import { safeAbsoluteHttpUrl } from "@/components/markdownSafeUrl";
import { useT } from "@/i18n";
import { ProjectCards } from "./ProjectCards";
import { EvalNumberedStack } from "./EvalNumberedStack";
import { EvalRichText } from "./EvalRichText";

/** Evidence card for one GitHub repository collected by the review agent. */
function RepoEvidenceCards({ items }: { items: RepoEvidence[] }) {
  const t = useT("resume");
  const cn = normalizeCnPunctuation;
  return (
    <section className="eval-section">
      <span className="eval-label">{t("projects.evidence")}</span>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {items.map((ev, i) => (
          <div key={i} className="surface-card !bg-surface-alt p-3.5 text-[12px] leading-relaxed">
            <div className="mb-1.5 flex items-center gap-2">
              <Github size={13} className="shrink-0 text-ink-subtle" />
              {/* repo_evidence.url is model-emitted: only absolute http(s)
                  URLs may become links (render-boundary guard mirroring the
                  backend normalize allowlist). */}
              <a
                href={safeAbsoluteHttpUrl(ev.url) || undefined}
                target="_blank"
                rel="noopener noreferrer"
                className="min-w-0 flex-1 truncate font-mono text-[12px] font-semibold text-[var(--primary)] hover:underline"
              >
                {ev.repo || t("projects.unknownRepo")}
              </a>
              {ev.stars != null && (
                <span className="flex shrink-0 items-center gap-1 text-[11px] text-ink-subtle">
                  <Star size={11} />
                  {ev.stars}
                </span>
              )}
              <ExternalLink size={11} className="shrink-0 text-ink-subtle" />
            </div>
            <p className="mb-1 text-[11px] text-ink-subtle">
              {[
                ev.language,
                ev.last_push ? t("projects.lastPush", { date: ev.last_push }) : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
            {ev.evidence_notes?.map((note, j) => (
              <p key={j} className="text-[11px] text-ink-subtle">
                {cn(note)}
              </p>
            ))}
            {ev.summary && (
              <p className="mt-1 line-clamp-4 text-ink-muted">
                <EvalRichText text={cn(ev.summary)} />
              </p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

/** Verdict card comparing one resume claim against repository facts. */
function RepoVerificationCards({ items }: { items: RepoVerification[] }) {
  const t = useT("resume");
  const cn = normalizeCnPunctuation;
  return (
    <section className="eval-section">
      <span className="eval-label">{t("projects.verification")}</span>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {items.map((v, i) => (
          <div key={i} className="surface-card !bg-surface-alt p-3.5">
            <p className="mb-1 font-mono text-[11px] text-ink-subtle">{v.repo}</p>
            <p className="text-[12px] font-semibold text-ink">{cn(v.verdict || "")}</p>
            {v.details && (
              <p className="mt-1 text-[12px] leading-relaxed text-ink-muted">
                <EvalRichText text={cn(v.details)} />
              </p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

export function ProjectsTab({ analysis }: { analysis: ResumeAnalysis }) {
  const t = useT("resume");
  const cn = normalizeCnPunctuation;
  return (
    <>
      {analysis.repo_evidence && analysis.repo_evidence.length > 0 && (
        <RepoEvidenceCards items={analysis.repo_evidence} />
      )}

      {analysis.repo_verification && analysis.repo_verification.length > 0 && (
        <RepoVerificationCards items={analysis.repo_verification} />
      )}

      {analysis.project_cards && analysis.project_cards.length > 0 && (
        <ProjectCards cards={analysis.project_cards} />
      )}

      {analysis.project_deep_dive && analysis.project_deep_dive.length > 0 && (
        <EvalNumberedStack
          title={t("projects.deepDive")}
          prefix="P"
          items={analysis.project_deep_dive.map(cn)}
        />
      )}

    </>
  );
}
