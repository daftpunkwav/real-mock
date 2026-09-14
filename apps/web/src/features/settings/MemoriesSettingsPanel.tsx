"use client";

/**
 * @file MemoriesSettingsPanel.tsx
 * @description Prep long-term memory management: searchable list, tag filter,
 * batch delete behind a confirm dialog, and per-memory editing.
 * Memories can only be edited or deleted here — creation happens in chat
 * (rating flow) or via the agent's memory_write tool.
 */

import { Brain, ChevronRight, Pencil, RotateCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Select } from "@/components/Select";
import { toast } from "@/components/Toast";
import { useT } from "@/i18n";
import { formatApiError } from "@/lib/api/base";
import { prepMemoryHttp } from "@/lib/api/prepMemoryHttp";
import type { PrepMemoryDetail, PrepMemorySummary } from "@/lib/api/contract";
import { cn } from "@/lib/utils";

const ORIGIN_KEYS = ["user_rating", "user_emphasis", "agent_note"] as const;

function originLabel(t: ReturnType<typeof useT>, origin: string): string {
  const key = `memories.origin.${(ORIGIN_KEYS as readonly string[]).includes(origin) ? origin : "agent_note"}` as
    | "memories.origin.user_rating"
    | "memories.origin.user_emphasis"
    | "memories.origin.agent_note";
  return t(key);
}

/** Full turn bodies of one memory (lazy-loaded on expand). */
function MemoryDetail({ detail }: { detail: PrepMemoryDetail }) {
  const t = useT("settings");
  return (
    <div className="mt-2 space-y-2 border-t border-surface-border pt-2">
      {detail.user_input && (
        <div>
          <p className="text-[11px] font-medium text-ink-muted">{t("memories.detailUserInput")}</p>
          <pre className="mt-0.5 max-h-40 overflow-y-auto whitespace-pre-wrap rounded bg-surface-muted px-2 py-1.5 text-[12px] leading-relaxed text-ink">
            {detail.user_input}
          </pre>
        </div>
      )}
      {detail.agent_output && (
        <div>
          <p className="text-[11px] font-medium text-ink-muted">{t("memories.detailAgentOutput")}</p>
          <pre className="mt-0.5 max-h-64 overflow-y-auto whitespace-pre-wrap rounded bg-surface-muted px-2 py-1.5 text-[12px] leading-relaxed text-ink">
            {detail.agent_output}
          </pre>
        </div>
      )}
      {detail.comment && (
        <div>
          <p className="text-[11px] font-medium text-ink-muted">{t("memories.detailComment")}</p>
          <p className="mt-0.5 whitespace-pre-wrap break-words text-[12px] leading-relaxed text-ink">
            {detail.comment}
          </p>
        </div>
      )}
      {(detail.reasons ?? []).length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] font-medium text-ink-muted">{t("memories.detailReasons")}</span>
          {(detail.reasons ?? []).map((reason) => (
            <span
              key={reason}
              className="rounded-full border border-surface-border px-2 py-0.5 text-[11px] text-ink-muted"
            >
              {reason}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** One memory row: summary + chips always visible, full bodies expandable. */
function MemoryRow({
  memory,
  open,
  detail,
  detailLoading,
  selected,
  onToggleSelect,
  onToggleOpen,
  onEdit,
}: {
  memory: PrepMemorySummary;
  open: boolean;
  detail?: PrepMemoryDetail;
  detailLoading: boolean;
  selected: boolean;
  onToggleSelect: () => void;
  onToggleOpen: () => void;
  onEdit: () => void;
}) {
  const t = useT("settings");
  return (
    <div className="flex items-start gap-2.5 p-3">
      <input
        type="checkbox"
        className="mt-1"
        checked={selected}
        onChange={onToggleSelect}
        aria-label={memory.summary}
      />
      <div className="min-w-0 flex-1">
        <button
          type="button"
          onClick={onToggleOpen}
          aria-expanded={open}
          aria-label={open ? t("memories.collapse") : t("memories.expand")}
          title={open ? t("memories.collapse") : t("memories.expand")}
          className="flex w-full items-start gap-1.5 text-left"
        >
          <ChevronRight
            size={13}
            className={cn(
              "mt-0.5 shrink-0 text-ink-subtle transition-transform",
              open && "rotate-90",
            )}
          />
          <span className="min-w-0 flex-1 break-words text-[13px] leading-relaxed text-ink">
            {memory.summary}
          </span>
        </button>
        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px]">
          <span className="rounded bg-surface-muted px-1.5 py-0.5 text-ink-subtle">
            {originLabel(t, memory.origin)}
          </span>
          {memory.score !== null && memory.score !== undefined && (
            <span className="rounded bg-[var(--warning-soft)] px-1.5 py-0.5 text-[var(--warning-ink)]">
              {memory.score}/10
            </span>
          )}
          {(memory.tags ?? []).map((tag) => (
            <span
              key={tag}
              className="rounded bg-[var(--info-soft)] px-1.5 py-0.5 text-[var(--info-ink)]"
            >
              {tag}
            </span>
          ))}
        </div>
        {open &&
          (detail ? (
            <MemoryDetail detail={detail} />
          ) : (
            <p className="mt-2 text-[12px] text-ink-subtle">
              {detailLoading ? t("memories.detailLoading") : null}
            </p>
          ))}
      </div>
      <button
        type="button"
        onClick={onEdit}
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded text-ink-subtle",
          "transition-colors hover:bg-surface-muted hover:text-ink",
        )}
        aria-label={t("memories.edit")}
        title={t("memories.edit")}
      >
        <Pencil size={13} />
      </button>
    </div>
  );
}

function MemoryEditDialog({
  memory,
  busy,
  onSave,
  onClose,
}: {
  memory: PrepMemoryDetail;
  busy: boolean;
  onSave: (patch: { comment: string; score: number | null }) => void;
  onClose: () => void;
}) {
  const t = useT("settings");
  const [comment, setComment] = useState(memory.comment);
  const [scoreText, setScoreText] = useState(memory.score === null ? "" : String(memory.score));

  const handleSave = () => {
    const score = scoreText.trim() === "" ? null : Number(scoreText);
    if (score !== null && (!Number.isInteger(score) || score < 1 || score > 10)) return;
    onSave({ comment, score });
  };

  const scoreNumber = scoreText.trim() === "" ? null : Number(scoreText);
  const scoreInvalid =
    scoreNumber !== null && (!Number.isInteger(scoreNumber) || scoreNumber < 1 || scoreNumber > 10);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Portal out of the page tree: entrance animations above retain an identity
  // transform, which would otherwise contain this fixed overlay to a content
  // box instead of the viewport (partial dimming).
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex overflow-y-auto bg-black/40 p-4 anim-fade-in"
      role="dialog"
      aria-modal="true"
      aria-label={t("memories.editTitle")}
    >
      <div className="surface-card m-auto max-h-[90vh] w-full max-w-lg overflow-y-auto !p-5 anim-rise">
        <h2 className="text-[14px] font-semibold text-ink">{t("memories.editTitle")}</h2>
        <div className="mt-3">
          <p className="text-[12px] font-medium text-ink-muted">
            {t("memories.summary")} · {t("memories.agentMaintained")}
          </p>
          <p className="mt-1 break-words rounded bg-surface-muted px-2.5 py-2 text-[13px] leading-relaxed text-ink">
            {memory.summary}
          </p>
        </div>
        <div className="mt-2.5">
          <p className="text-[12px] font-medium text-ink-muted">
            {t("memories.tagsTitle")} · {t("memories.agentMaintained")}
          </p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {(memory.tags ?? []).map((tag) => (
              <span
                key={tag}
                className="rounded bg-[var(--info-soft)] px-2 py-0.5 text-[11px] text-[var(--info-ink)]"
              >
                {tag}
              </span>
            ))}
          </div>
        </div>
        <label className="mt-2.5 block text-[12px] font-medium text-ink-muted">
          {t("memories.comment")}
          <textarea
            className="field-input mt-1 min-h-16 w-full resize-y"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            disabled={busy}
            maxLength={2000}
          />
        </label>
        <label className="mt-2.5 block text-[12px] font-medium text-ink-muted">
          {t("memories.score")}
          <input
            className="field-input mt-1 w-24"
            value={scoreText}
            onChange={(e) => setScoreText(e.target.value.replace(/[^0-9]/g, "").slice(0, 2))}
            disabled={busy}
            inputMode="numeric"
          />
        </label>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="btn-ghost h-9 shrink-0 whitespace-nowrap px-4"
          >
            {t("memories.cancel")}
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={busy || scoreInvalid}
            className="btn-primary h-9 shrink-0 whitespace-nowrap px-5"
          >
            {t("memories.save")}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

export function MemoriesSettingsPanel() {
  const t = useT("settings");
  const [items, setItems] = useState<PrepMemorySummary[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [selected, setSelected] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [editing, setEditing] = useState<PrepMemoryDetail | null>(null);
  const [openIds, setOpenIds] = useState<number[]>([]);
  const [details, setDetails] = useState<Record<number, PrepMemoryDetail>>({});
  const [detailLoadingId, setDetailLoadingId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [list, tagRes] = await Promise.all([
        prepMemoryHttp.listMemories(tagFilter || undefined, 100),
        prepMemoryHttp.listTags(),
      ]);
      setItems(Array.isArray(list) ? list : []);
      setTags(tagRes.tags ?? []);
      setSelected([]);
    } catch (err) {
      toast.error(err instanceof Error ? formatApiError(err) : t("memories.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [tagFilter, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((m) => m.summary.toLowerCase().includes(q));
  }, [items, query]);

  const toggle = (id: number) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const toggleAll = () => {
    setSelected((prev) => (prev.length === visible.length ? [] : visible.map((m) => m.id)));
  };

  const handleBatchDelete = async () => {
    setBusy(true);
    try {
      await prepMemoryHttp.batchRemove(selected);
      setConfirming(false);
      toast.success(t("memories.batchDeleted", { count: selected.length }));
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? formatApiError(err) : t("memories.deleteFailed"));
      throw err;
    } finally {
      setBusy(false);
    }
  };

  const openEdit = async (id: number) => {
    try {
      setEditing(await prepMemoryHttp.getDetail(id));
    } catch (err) {
      toast.error(err instanceof Error ? formatApiError(err) : t("memories.loadFailed"));
    }
  };

  const handleSaveEdit = async (patch: { comment: string; score: number | null }) => {
    if (!editing) return;
    setBusy(true);
    try {
      const updated = await prepMemoryHttp.update(editing.id, patch);
      setDetails((prev) => ({ ...prev, [updated.id]: updated }));
      setEditing(null);
      toast.success(t("memories.saved"));
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? formatApiError(err) : t("memories.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  const toggleOpen = async (id: number) => {
    if (openIds.includes(id)) {
      setOpenIds((prev) => prev.filter((x) => x !== id));
      return;
    }
    setOpenIds((prev) => [...prev, id]);
    if (details[id] || detailLoadingId === id) return;
    setDetailLoadingId(id);
    try {
      const detail = await prepMemoryHttp.getDetail(id);
      setDetails((prev) => ({ ...prev, [id]: detail }));
    } catch (err) {
      setOpenIds((prev) => prev.filter((x) => x !== id));
      toast.error(err instanceof Error ? formatApiError(err) : t("memories.loadFailed"));
    } finally {
      setDetailLoadingId(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="surface-card p-4">
        <div className="mb-1 flex items-center gap-2">
          <Brain size={16} className="text-[var(--primary)]" />
          <h2 className="text-[14px] font-semibold">{t("memories.title")}</h2>
        </div>
        <p className="text-[13px] leading-relaxed text-ink-muted">{t("memories.desc")}</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input
            className="field-input min-w-40 flex-1"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("memories.searchPlaceholder")}
          />
          <Select
            className="w-36"
            ariaLabel={t("memories.tagFilter")}
            value={tagFilter}
            options={[
              { value: "", label: t("memories.tagAll") },
              ...tags.map((tag) => ({ value: tag, label: tag })),
            ]}
            onChange={setTagFilter}
          />
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="btn-ghost !h-9 !w-9 !px-0"
            aria-label={t("memories.reload")}
          >
            <RotateCw size={14} className={loading ? "anim-spin" : undefined} />
          </button>
        </div>
      </div>

      {selected.length > 0 && (
        <div className="surface-card flex items-center justify-between gap-2 p-3">
          <span className="text-[13px] text-ink-muted">
            {t("memories.selected", { count: selected.length })}
          </span>
          <button
            type="button"
            onClick={() => setConfirming(true)}
            disabled={busy}
            className="inline-flex h-9 items-center rounded-md border border-[var(--danger)]/30 bg-surface-alt px-4 text-[13px] font-medium text-[var(--danger-ink)] transition-colors hover:bg-[var(--danger-soft)] disabled:opacity-45"
          >
            {t("memories.batchDelete")}
          </button>
        </div>
      )}

      <div className="surface-card divide-y divide-[var(--border)]">
        <label className="flex items-center gap-2.5 p-3 text-[12px] text-ink-muted">
          <input type="checkbox" checked={visible.length > 0 && selected.length === visible.length} onChange={toggleAll} />
          {t("memories.selectAll")}
        </label>
        {visible.length === 0 && (
          <p className="p-4 text-[13px] text-ink-subtle">{t("memories.empty")}</p>
        )}
        {visible.map((m) => (
          <MemoryRow
            key={m.id}
            memory={m}
            open={openIds.includes(m.id)}
            detail={details[m.id]}
            detailLoading={detailLoadingId === m.id}
            selected={selected.includes(m.id)}
            onToggleSelect={() => toggle(m.id)}
            onToggleOpen={() => void toggleOpen(m.id)}
            onEdit={() => void openEdit(m.id)}
          />
        ))}
      </div>

      <ConfirmDialog
        open={confirming}
        title={t("memories.confirmTitle")}
        message={t("memories.confirmBody", { count: selected.length })}
        confirmLabel={t("memories.batchDelete")}
        cancelLabel={t("memories.cancel")}
        busy={busy}
        onConfirm={() => void handleBatchDelete()}
        onCancel={() => setConfirming(false)}
      />
      {editing && (
        <MemoryEditDialog
          memory={editing}
          busy={busy}
          onSave={(patch) => void handleSaveEdit(patch)}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}
