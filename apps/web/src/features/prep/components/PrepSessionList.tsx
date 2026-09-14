"use client";

/**
 * @file PrepSessionList.tsx
 * @description Conversation history grouped by resume: active sessions plus a
 * collapsed archive. Rows expose hover actions (archive/restore, clear, delete)
 * behind a shared confirm dialog.
 */

import { memo, useMemo, useState } from "react";
import { Archive, ArchiveRestore, ChevronRight, Eraser, MessageSquare, Plus, Square, Trash2 } from "lucide-react";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { useT, type Translator } from "@/i18n";
import type { PrepSessionSummary } from "@/lib/api/contract";
import { cn } from "@/lib/utils";

/** Relative time label; falls back to M-D after 7 days. */
function relativeTime(iso: string, t: Translator<"prep">): string {
  const time = Date.parse(iso);
  if (Number.isNaN(time)) return "";
  const min = Math.floor((Date.now() - time) / 60000);
  if (min < 1) return t("sessions.time.justNow");
  if (min < 60) return t("sessions.time.minutesAgo", { n: min });
  const hr = Math.floor(min / 60);
  if (hr < 24) return t("sessions.time.hoursAgo", { n: hr });
  const day = Math.floor(hr / 24);
  if (day < 7) return t("sessions.time.daysAgo", { n: day });
  const d = new Date(time);
  return `${d.getMonth() + 1}-${d.getDate()}`;
}

type PendingAction =
  | { kind: "delete"; id: number }
  | { kind: "archive"; id: number; archived: boolean }
  | { kind: "clear"; id: number }
  | null;

function RowAction({
  title,
  onClick,
  children,
}: {
  title: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className="flex h-6 w-6 shrink-0 items-center justify-center rounded text-ink-subtle opacity-0 transition-all hover:bg-surface-muted hover:text-ink focus-visible:opacity-100 group-hover:opacity-100"
    >
      {children}
    </button>
  );
}

function SessionRow({
  session,
  currentId,
  summaryFallback,
  timeText,
  generatingText,
  generating,
  onSelect,
  onAction,
  onStop,
}: {
  session: PrepSessionSummary;
  currentId: number | null;
  summaryFallback: string;
  timeText: string;
  generatingText: string;
  generating: boolean;
  onSelect: (id: number) => void;
  onAction: (action: Exclude<PendingAction, null>) => void;
  onStop: (id: number) => void;
}) {
  const t = useT("prep");
  const active = session.id === currentId;
  const archived = session.status === "archived";
  return (
    <div
      className={cn(
        "group flex items-start gap-1 rounded-md border px-2 py-1.5 transition-colors",
        active
          ? "border-[var(--primary)] bg-[var(--info-soft)]"
          : "border-surface-border hover:border-[var(--primary)] hover:bg-surface-muted",
      )}
    >
      <button
        type="button"
        onClick={() => onSelect(session.id)}
        className="min-w-0 flex-1 text-left"
      >
        <span className="flex items-center gap-1.5 truncate text-[12px] leading-snug text-ink">
          {generating && (
            <span
              className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-[var(--primary)]"
              title={generatingText}
              aria-label={generatingText}
              role="status"
            />
          )}
          <span className="truncate">{session.summary || summaryFallback}</span>
        </span>
        <span className="mt-0.5 block text-[10px] text-ink-subtle">{timeText}</span>
      </button>
      <div className="flex shrink-0 items-center pt-0.5">
        {generating && (
          <RowAction
            title={t("sessions.stopGeneration")}
            onClick={() => onStop(session.id)}
          >
            <Square size={12} fill="currentColor" />
          </RowAction>
        )}
        <RowAction
          title={archived ? t("sessions.unarchive") : t("sessions.archive")}
          onClick={() => onAction({ kind: "archive", id: session.id, archived: !archived })}
        >
          {archived ? <ArchiveRestore size={13} /> : <Archive size={13} />}
        </RowAction>
        <RowAction
          title={t("sessions.clear")}
          onClick={() => onAction({ kind: "clear", id: session.id })}
        >
          <Eraser size={13} />
        </RowAction>
        <RowAction
          title={t("sessions.delete")}
          onClick={() => onAction({ kind: "delete", id: session.id })}
        >
          <Trash2 size={13} />
        </RowAction>
      </div>
    </div>
  );
}

interface PrepSessionListProps {
  sessions: PrepSessionSummary[];
  currentId: number | null;
  creating?: boolean;
  /** Sessions with a live generation stream (pulsing dot + stop action). */
  busySids?: readonly number[];
  onSelect: (id: number) => void;
  onNew: () => void;
  onDelete: (id: number) => void;
  onArchive: (id: number, archived: boolean) => void;
  onClear: (id: number) => void;
  /** Stop a background generation; defaults to a no-op when unwired. */
  onStop?: (id: number) => void;
}

/**
 * Conversation history grouped by resume: active sessions plus a collapsed
 * archive. Rows expose hover actions (stop generation while streaming,
 * archive/restore, clear, delete) behind a shared confirm dialog.
 * Destructive actions confirm; stopping a generation applies immediately.
 */
export const PrepSessionList = memo(function PrepSessionList({
  sessions,
  currentId,
  creating = false,
  busySids,
  onSelect,
  onNew,
  onDelete,
  onArchive,
  onClear,
  onStop,
}: PrepSessionListProps) {
  const t = useT("prep");
  const [showArchived, setShowArchived] = useState(false);
  const [pending, setPending] = useState<PendingAction>(null);
  const [busy, setBusy] = useState(false);

  const { activeGroups, archived } = useMemo(() => {
    const map = new Map<string, { id: string; label: string; items: PrepSessionSummary[] }>();
    const archivedItems: PrepSessionSummary[] = [];
    for (const s of sessions) {
      if (s.status === "archived") {
        archivedItems.push(s);
        continue;
      }
      const key = s.resume_id != null ? `r${s.resume_id}` : "none";
      if (!map.has(key))
        map.set(key, { id: key, label: s.resume_filename || t("sessions.genericGroup"), items: [] });
      map.get(key)!.items.push(s);
    }
    return { activeGroups: [...map.values()], archived: archivedItems };
  }, [sessions, t]);

  const confirmCopy =
    pending?.kind === "delete"
      ? { title: t("sessions.deleteTitle"), body: t("sessions.deleteBody"), action: t("sessions.delete") }
      : pending?.kind === "archive"
        ? pending.archived
          ? { title: t("sessions.archiveTitle"), body: t("sessions.archiveBody"), action: t("sessions.archive") }
          : { title: t("sessions.unarchiveTitle"), body: t("sessions.unarchiveBody"), action: t("sessions.unarchive") }
        : { title: t("sessions.clearTitle"), body: t("sessions.clearBody"), action: t("sessions.clear") };

  const runPending = async () => {
    if (!pending) return;
    setBusy(true);
    try {
      if (pending.kind === "delete") await onDelete(pending.id);
      else if (pending.kind === "archive") await onArchive(pending.id, pending.archived);
      else await onClear(pending.id);
      setPending(null);
    } finally {
      setBusy(false);
    }
  };

  const rowProps = (s: PrepSessionSummary) => ({
    currentId,
    summaryFallback: t("sessions.newSessionFallback"),
    timeText: `${relativeTime(s.updated_at, t) || "—"} · ${t("sessions.messageCount", { count: s.message_count })}`,
    generatingText: t("sessions.generating"),
    generating: busySids?.includes(s.id) ?? false,
    onSelect,
    onAction: setPending,
    onStop: onStop ?? (() => {}),
  });

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
          <MessageSquare size={14} className="text-[var(--primary)]" />
          {t("sessions.title")}
        </h2>
        <button
          type="button"
          onClick={onNew}
          disabled={creating}
          className="flex items-center gap-1 rounded-md border border-surface-border px-2 py-1 text-[11px] font-medium text-ink-muted transition-colors hover:border-[var(--primary)] hover:bg-[var(--info-soft)] hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Plus size={12} />
          {t("sessions.new")}
        </button>
      </div>

      {sessions.length === 0 ? (
        <p className="text-[11px] leading-relaxed text-ink-subtle">
          {t("sessions.empty")}
        </p>
      ) : (
        <div className="max-h-[280px] space-y-3 overflow-y-auto pr-0.5 [scrollbar-gutter:stable]">
          {activeGroups.map((g) => (
            <div key={g.id}>
              <p className="mb-1 truncate text-[10px] font-medium uppercase tracking-wider text-ink-subtle">
                {g.label}
              </p>
              <div className="space-y-1">
                {g.items.map((s) => (
                  <SessionRow key={s.id} session={s} {...rowProps(s)} />
                ))}
              </div>
            </div>
          ))}
          {archived.length > 0 && (
            <div>
              <button
                type="button"
                onClick={() => setShowArchived((v) => !v)}
                aria-expanded={showArchived}
                className="mb-1 flex w-full items-center gap-1 text-[10px] font-medium uppercase tracking-wider text-ink-subtle transition-colors hover:text-ink"
              >
                <ChevronRight
                  size={12}
                  className={cn("transition-transform", showArchived && "rotate-90")}
                />
                {t("sessions.archivedTitle", { count: archived.length })}
              </button>
              {showArchived && (
                <div className="space-y-1">
                  {archived.map((s) => (
                    <SessionRow key={s.id} session={s} {...rowProps(s)} />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <ConfirmDialog
        open={pending !== null}
        title={confirmCopy.title}
        message={confirmCopy.body}
        confirmLabel={confirmCopy.action}
        cancelLabel={t("sessions.cancelAction")}
        busy={busy}
        onConfirm={() => void runPending()}
        onCancel={() => setPending(null)}
      />
    </div>
  );
});
