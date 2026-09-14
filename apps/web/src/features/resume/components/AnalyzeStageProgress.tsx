"use client";

/**
 * @file AnalyzeStageProgress.tsx
 * @description Live review desk: plan spine on the left, execution log on the right.
 *
 * Row rendering lives in ./analysis-progress (PlanSpine / ThinkingRow /
 * ToolRow); this module only owns open-row state, the ticking clock, and
 * layout. Order matches SSE occurrence, not a fake carousel.
 */

import { useEffect, useState } from "react";
import { useT } from "@/i18n";
import type { ReviewLiveState, ReviewTimelineItem } from "../reviewProgress";
import { PlanSpine } from "./analysis-progress/PlanSpine";
import { ThinkingRow } from "./analysis-progress/ThinkingRow";
import { NoticeRow } from "./analysis-progress/NoticeRow";
import { ToolRow } from "./analysis-progress/ToolRow";
import { useStickToBottom } from "./analysis-progress/useStickToBottom";

export function AnalyzeStageProgress({ progress }: { progress?: ReviewLiveState }) {
  const t = useT("resume");
  const steps = progress?.steps ?? [];
  const timeline = progress?.timeline ?? [];
  const [openIds, setOpenIds] = useState<Record<string, boolean>>({});
  const [now, setNow] = useState(() => Date.now());
  const log = useStickToBottom(timeline.length);

  const thinkingOpen = timeline.some((item) => item.kind === "thinking" && item.endedAt == null);
  useEffect(() => {
    if (!thinkingOpen) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [thinkingOpen]);

  const toggle = (id: string) => {
    setOpenIds((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div className="px-5 py-5 sm:px-7 sm:py-6">
      <div className="grid min-h-[22rem] grid-cols-1 gap-5 md:grid-cols-[minmax(13rem,17rem)_minmax(0,1fr)] md:gap-0">
        <section
          aria-label={t("stage.plan")}
          className="md:border-r md:border-surface-border md:pr-6"
        >
          <p className="mb-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-subtle">
            {t("stage.plan")}
          </p>
          <PlanSpine steps={steps} />
        </section>

        <section aria-label={t("stage.log")} className="flex min-h-0 flex-col md:pl-6">
          <p className="mb-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-subtle">
            {t("stage.log")}
          </p>
          <div
            ref={log.ref}
            onScroll={log.onScroll}
            aria-live="polite"
            className="min-h-0 max-h-[min(70vh,36rem)] flex-1 space-y-0.5 overflow-y-auto pr-1"
          >
            {timeline.length === 0 ? (
              <p className="text-[12px] text-ink-subtle">{t("stage.emptyLog")}</p>
            ) : (
              timeline.map((item: ReviewTimelineItem) =>
                item.kind === "thinking" ? (
                  <ThinkingRow
                    key={item.id}
                    item={item}
                    now={now}
                    expanded={Boolean(openIds[item.id])}
                    onToggle={() => toggle(item.id)}
                  />
                ) : item.kind === "notice" ? (
                  <NoticeRow key={item.id} item={item} />
                ) : (
                  <ToolRow
                    key={item.id}
                    item={item}
                    expanded={Boolean(openIds[item.id])}
                    onToggle={() => toggle(item.id)}
                  />
                ),
              )
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
