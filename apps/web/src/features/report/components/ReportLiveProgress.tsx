"use client";

/** Live view of the two-stage report agent: stage / tool / thinking events. */

import { useT, type Translator } from "@/i18n";
import type { ReportLiveState } from "../liveEvents";

function eventLine(
  t: Translator<"report">,
  event: ReportLiveState["events"][number],
): string {
  if (event.type === "stage") {
    return event.stage === "synthesis" ? t("live.stageSynthesis") : t("live.stageNotes");
  }
  if (event.type === "tool_step") {
    return event.name ? t("live.tool", { name: event.name }) : t("live.working");
  }
  return event.content ? event.content : t("live.thinking");
}

export function ReportLiveProgress({ live }: { live: ReportLiveState }) {
  const t = useT("report");
  return (
    <div className="page-shell-tight anim-rise">
      <div className="surface-card p-5">
        <div className="mb-4 flex items-center gap-2.5">
          <span className="block h-4 w-4 anim-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
          <h2 className="text-[13px] font-semibold tracking-tight text-ink">
            {t("live.title")}
          </h2>
        </div>
        {live.events.length === 0 ? (
          <p className="text-[12px] text-ink-muted">{t("live.starting")}</p>
        ) : (
          <ol className="space-y-1.5">
            {live.events.map((event, i) => (
              <li key={i} className="flex items-start gap-2 text-[12px] text-ink-muted">
                <span className="mt-1.5 inline-block h-1 w-1 shrink-0 rounded-full bg-[var(--primary)] opacity-60" />
                <span className="min-w-0 break-words">{eventLine(t, event)}</span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
