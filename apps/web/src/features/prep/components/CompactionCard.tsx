"use client";

/**
 * @file CompactionCard.tsx
 * @description Persisted compaction-summary record rendered as a centered
 * timeline divider — deliberately NOT an agent bubble (no avatar, no reply
 * chrome): a slim pill with version and token delta, expanding into the full
 * summary plus view/edit/regenerate/fork actions. Rule-fallback digests
 * (version 0) render read-only without edit/regenerate actions.
 */

import { useState } from "react";
import { ChevronRight, Shrink } from "lucide-react";
import { useT } from "@/i18n";
import { toast } from "@/components/Toast";
import { MarkdownContent } from "@/components/MarkdownContent";
import { formatApiError } from "@/lib/api/base";
import { formatTokens } from "@/components/ModelControls";
import { cn } from "@/lib/utils";
import type { PrepChatMessage } from "../types";

export interface CompactionCardActions {
  /** Fork the backup session through up_to (or -1 for the whole record). */
  onForkFromPoint: (backupSessionId: number, upTo: number) => void;
  /** Open the archived pre-compaction backup session. */
  onOpenBackup: (backupSessionId: number) => void;
  /** Persist an edited summary (with one concurrency retry), then reload. */
  onSaveEdit: (sessionId: number, text: string) => Promise<void>;
  /** Reload history after an edit. */
  onReload: () => void;
  /** Archive-aware regeneration with fresh settings params. */
  onRegenerate: () => void;
}

export function CompactionCard({
  msg,
  sessionId,
  actions,
  disabled,
}: {
  msg: PrepChatMessage;
  sessionId: number | null;
  actions: CompactionCardActions;
  /** True while the session streams (regeneration would clobber the turn). */
  disabled?: boolean;
}) {
  const t = useT("prep");
  const card = msg.compaction;
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  if (!card) return null;
  const editable = card.version > 0;
  const busyAll = busy || disabled;

  const saveEdit = async () => {
    if (sessionId === null || !draft.trim()) return;
    setBusy(true);
    try {
      await actions.onSaveEdit(sessionId, draft.trim());
      toast.success(t("compactCard.saved"));
      setEditing(false);
      actions.onReload();
    } catch (err) {
      toast.error(err instanceof Error ? formatApiError(err) : t("compactCard.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  const regenerate = () => {
    // Archive-aware regenerate flow with fresh settings params (no new
    // backup); notices and reloads run through the shared handler.
    actions.onRegenerate();
  };

  return (
    <div className="flex justify-center px-4" data-compaction-card={msg.id}>
      <div className="w-full max-w-[88%] rounded-md border border-dashed border-surface-border bg-surface-muted px-3 py-1.5">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="flex w-full items-center gap-2 text-left text-[11px] text-ink-muted"
        >
          <Shrink size={12} className="shrink-0 text-[var(--primary)]" />
          <span className="font-medium">
            {editable
              ? t("compactCard.title", { version: card.version })
              : t("compactCard.digestTitle")}
            {card.before !== null && card.after !== null
              ? ` · ${t("compactCard.tokens", { before: formatTokens(card.before), after: formatTokens(card.after) })}`
              : null}
          </span>
          <ChevronRight
            size={12}
            className={cn("ml-auto shrink-0 text-ink-subtle transition-transform", expanded && "rotate-90")}
          />
        </button>
        {expanded && (
          <div className="mt-1.5 border-t border-dashed border-surface-border pt-1.5 text-[13px] leading-relaxed text-ink">
            {editing ? (
              <div className="space-y-2">
                <textarea
                  className="input min-h-20 w-full text-[13px]"
                  rows={4}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder={t("compactCard.editPlaceholder")}
                />
                <div className="flex gap-2">
                  <button type="button" className="btn-primary text-[12px]" disabled={busyAll || !draft.trim()} onClick={() => void saveEdit()}>
                    {t("compactCard.save")}
                  </button>
                  <button type="button" className="btn-secondary text-[12px]" disabled={busy} onClick={() => setEditing(false)}>
                    {t("compactCard.cancel")}
                  </button>
                </div>
              </div>
            ) : (
              <MarkdownContent content={msg.content} />
            )}
            {!editing ? (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {editable ? (
                  <button
                    type="button"
                    className="btn-secondary text-[12px]"
                    onClick={() => {
                      setDraft(msg.content);
                      setEditing(true);
                    }}
                  >
                    {t("compactCard.edit")}
                  </button>
                ) : null}
            {editable ? (
              <button type="button" className="btn-secondary text-[12px]" disabled={busyAll} onClick={regenerate}>
                {t("compactCard.regenerate")}
              </button>
            ) : null}
                {card.backupSessionId !== null && card.forkPoint !== null ? (
                  <button
                    type="button"
                    className="btn-secondary text-[12px]"
                    onClick={() => actions.onForkFromPoint(card.backupSessionId as number, card.forkPoint as number)}
                  >
                    {t("compactCard.forkFromPoint")}
                  </button>
                ) : null}
                {card.backupSessionId !== null ? (
                  <button
                    type="button"
                    className="btn-secondary text-[12px]"
                    onClick={() => actions.onOpenBackup(card.backupSessionId as number)}
                  >
                    {t("compactCard.viewBackup")}
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
