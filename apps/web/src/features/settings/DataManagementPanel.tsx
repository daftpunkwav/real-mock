"use client";

/**
 * @file DataManagementPanel.tsx
 * @description Data category: per-item export (report / record / analysis,
 * markdown or JSON) and the wipe-everything destructive action.
 *
 * Export keeps one card: pick the data kind, the item, and the format; the
 * download streams through the shared downloadTextFile helper. The wipe is
 * gated behind a two-step dialog — open + tick an acknowledgement checkbox
 * before the confirm button unlocks.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Download, HardDriveDownload, TriangleAlert } from "lucide-react";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Spinner } from "@/components/Spinner";
import { toast } from "@/components/Toast";
import { useT } from "@/i18n";
import { downloadTextFile } from "@/lib/download";
import { formatApiError } from "@/lib/api/base";
import { recordsHttp, resumeHttp, settingsHttp } from "@/lib/api/clients";
import type { ResumeResponse } from "@/lib/api/contract";
import type { SessionHistoryItem } from "@/types/domains/records";

type ExportKind = "report" | "record" | "analysis";
type ExportFormat = "md" | "json";

/** Item picker row shared by the kind-dependent selects. */
function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[96px_minmax(0,1fr)] items-center gap-2 sm:grid-cols-[120px_minmax(0,1fr)]">
      <span className="text-[12px] text-ink-subtle">{label}</span>
      {children}
    </div>
  );
}

/** Label shown for one session row in the item picker. */
function sessionLabel(s: SessionHistoryItem): string {
  const date = (s.created_at || s.started_at || "").slice(0, 10);
  const who = [s.role, s.company].filter(Boolean).join(" · ");
  return `#${s.id}${who ? ` ${who}` : ""}${date ? ` ${date}` : ""}`;
}

/** Result of one picker fetch: the rows plus the first id to preselect. */
interface PickedList<T> {
  rows: T[];
  firstId: number | null;
}

/**
 * Fetch one picker list under the given alive guard: null-safe rows on
 * success, an empty list on failure. Returns the snapshot to commit.
 */
async function fetchPickerList<T extends { id: number }>(
  alive: () => boolean,
  load: () => Promise<T[]>,
): Promise<PickedList<T>> {
  try {
    const fetched = await load();
    const rows = alive() && Array.isArray(fetched) ? fetched : [];
    return { rows, firstId: rows[0]?.id ?? null };
  } catch {
    return { rows: alive() ? [] : [], firstId: null };
  }
}

/** The three export kinds with their picker wiring and fetch call. */
const EXPORT_KINDS: readonly {
  value: ExportKind;
  labelKey: "data.export.kindReport" | "data.export.kindRecord" | "data.export.kindAnalysis";
}[] = [
  { value: "report", labelKey: "data.export.kindReport" },
  { value: "record", labelKey: "data.export.kindRecord" },
  { value: "analysis", labelKey: "data.export.kindAnalysis" },
];

/** One item of the kind or format segmented pickers. */
function PickerOption({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`rounded-md border px-3 py-1.5 text-[12px] font-medium transition-colors ${
        selected
          ? "border-[var(--primary)] bg-[var(--info-soft)] text-ink"
          : "border-surface-border text-ink-muted hover:border-[var(--primary)] hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}

/** One option row of a picker select (or a placeholder when empty). */
function PickerSelect<T extends { id: number }>({
  value,
  items,
  disabled,
  emptyLabel,
  label,
  renderLabel,
  onChange,
}: {
  value: number | null;
  items: T[];
  disabled: boolean;
  emptyLabel: string;
  label: string;
  renderLabel: (item: T) => string;
  onChange: (id: number | null) => void;
}) {
  return (
    <FieldRow label={label}>
      <select
        className="field-select !h-9 !text-[13px] disabled:opacity-60"
        value={value ?? ""}
        disabled={disabled}
        onChange={(e) => {
          onChange(e.target.value ? Number(e.target.value) : null);
        }}
      >
        {items.length === 0 ? (
          <option value="">{emptyLabel}</option>
        ) : (
          items.map((item) => (
            <option key={item.id} value={item.id}>
              {renderLabel(item)}
            </option>
          ))
        )}
      </select>
    </FieldRow>
  );
}

/** Resume picker shown when the analysis kind is selected. */
function ResumePicker({
  resumes,
  resumeId,
  onChange,
}: {
  resumes: ResumeResponse[];
  resumeId: number | null;
  onChange: (id: number | null) => void;
}) {
  const t = useT("settings");
  return (
    <PickerSelect
      label={t("data.export.item")}
      value={resumeId}
      items={resumes}
      disabled={resumes.length === 0}
      emptyLabel={t("data.export.noResumes")}
      renderLabel={(r) => r.filename}
      onChange={onChange}
    />
  );
}

/** Session picker shown for the report/record kinds. */
function SessionPicker({
  sessions,
  sessionId,
  onChange,
}: {
  sessions: SessionHistoryItem[];
  sessionId: number | null;
  onChange: (id: number | null) => void;
}) {
  const t = useT("settings");
  return (
    <PickerSelect
      label={t("data.export.item")}
      value={sessionId}
      items={sessions}
      disabled={sessions.length === 0}
      emptyLabel={t("data.export.noSessions")}
      renderLabel={sessionLabel}
      onChange={onChange}
    />
  );
}

/** Arguments identifying one export the user asked for. */
interface ExportRequest {
  kind: ExportKind;
  format: ExportFormat;
  sessionId: number | null;
  resumeId: number | null;
  includeResume: boolean;
}

/** Fetch the export file for one request, or null when its item is unset. */
async function requestExportFile(req: ExportRequest) {
  if (req.kind === "analysis") {
    if (req.resumeId == null) return null;
    return resumeHttp.exportAnalysis(req.resumeId, req.format, req.includeResume);
  }
  if (req.sessionId == null) return null;
  return req.kind === "report"
    ? recordsHttp.exportReport(req.sessionId, req.format)
    : recordsHttp.exportRecord(req.sessionId, req.format);
}

/** Export card: kind/item/format pickers plus the download action. */
function ExportCard({
  sessions,
  resumes,
  onExported,
}: {
  sessions: SessionHistoryItem[];
  resumes: ResumeResponse[];
  onExported: () => void;
}) {
  const t = useT("settings");
  const [kind, setKind] = useState<ExportKind>("report");
  const [format, setFormat] = useState<ExportFormat>("md");
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [resumeId, setResumeId] = useState<number | null>(null);
  const [includeResume, setIncludeResume] = useState(false);
  const [exporting, setExporting] = useState(false);

  const isAnalysis = kind === "analysis";
  const itemReady = isAnalysis ? resumeId != null : sessionId != null;

  const handleExport = async () => {
    if (exporting) return;
    setExporting(true);
    try {
      const file = await requestExportFile({ kind, format, sessionId, resumeId, includeResume });
      // A null file means the kind's picker lost its selection mid-flight;
      // the item is simply not exported.
      if (file) {
        downloadTextFile(file.filename, file.content, file.mime);
        toast.success(t("data.export.done", { name: file.filename }));
        onExported();
      }
    } catch (err) {
      toast.error(err instanceof Error ? formatApiError(err) : t("data.export.failed"));
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="surface-card p-4">
      <div className="mb-1 flex items-center gap-2">
        <Download size={16} className="text-[var(--primary)]" />
        <h2 className="text-[14px] font-semibold">{t("data.export.title")}</h2>
      </div>
      <p className="mb-3 text-[13px] leading-relaxed text-ink-muted">{t("data.export.desc")}</p>

      <div className="space-y-2.5">
        <FieldRow label={t("data.export.kind")}>
          <select
            className="field-select !h-9 !text-[13px]"
            value={kind}
            onChange={(e) => {
              setKind(e.target.value as ExportKind);
            }}
          >
            {EXPORT_KINDS.map((o) => (
              <option key={o.value} value={o.value}>
                {t(o.labelKey)}
              </option>
            ))}
          </select>
        </FieldRow>

        {isAnalysis ? (
          <ResumePicker resumes={resumes} resumeId={resumeId} onChange={setResumeId} />
        ) : (
          <SessionPicker sessions={sessions} sessionId={sessionId} onChange={setSessionId} />
        )}

        {isAnalysis && (
          <label className="flex cursor-pointer items-center gap-2 pl-[96px] sm:pl-[120px]">
            <input
              type="checkbox"
              className="h-3.5 w-3.5 accent-[var(--primary)]"
              checked={includeResume}
              onChange={(e) => {
                setIncludeResume(e.target.checked);
              }}
            />
            <span className="text-[12px] text-ink-muted">{t("data.export.includeResume")}</span>
          </label>
        )}

        <FieldRow label={t("data.export.format")}>
          <div className="flex gap-1.5">
            {(["md", "json"] as const).map((f) => (
              <PickerOption key={f} selected={format === f} onClick={() => setFormat(f)}>
                {f === "md" ? t("data.export.formatMd") : t("data.export.formatJson")}
              </PickerOption>
            ))}
          </div>
        </FieldRow>
      </div>

      <button
        type="button"
        className="btn-primary mt-3 !h-9 text-[13px]"
        disabled={!itemReady || exporting}
        onClick={() => void handleExport()}
      >
        {exporting ? (
          <Spinner className="h-3.5 w-3.5" />
        ) : (
          <Download size={13} className="btn-arrow" />
        )}
        {t("data.export.action")}
      </button>
    </div>
  );
}

/** Destructive wipe card with its two-step confirmation dialog. */
function WipeCard({ onWiped }: { onWiped: () => void }) {
  const t = useT("settings");
  const tc = useT("common");
  const [wipeOpen, setWipeOpen] = useState(false);
  const [wiping, setWiping] = useState(false);

  const handleWipe = async () => {
    setWiping(true);
    try {
      await settingsHttp.clearAllData();
      toast.success(t("data.wipe.done"));
      // Clear busy before closing: the dialog restores focus to the wipe
      // trigger on close, and a disabled trigger would swallow it.
      setWiping(false);
      setWipeOpen(false);
      onWiped();
    } catch (err) {
      toast.error(err instanceof Error ? formatApiError(err) : t("data.wipe.failed"));
      setWiping(false);
    }
  };

  return (
    <div className="surface-card p-4">
      <div className="mb-1 flex items-center gap-2">
        <TriangleAlert size={16} className="text-[var(--danger)]" />
        <h2 className="text-[14px] font-semibold">{t("data.wipe.title")}</h2>
      </div>
      <p className="text-[13px] leading-relaxed text-ink-muted">{t("data.wipe.desc")}</p>
      <button
        type="button"
        className="btn-danger mt-3 text-[13px]"
        disabled={wiping}
        onClick={() => setWipeOpen(true)}
      >
        <HardDriveDownload size={13} className="rotate-180" />
        {t("data.wipe.action")}
      </button>

      <ConfirmDialog
        open={wipeOpen}
        title={t("data.wipe.confirmTitle")}
        message={t("data.wipe.confirmBody")}
        confirmLabel={t("data.wipe.action")}
        cancelLabel={tc("confirm.cancel")}
        busy={wiping}
        requireAcknowledgement
        acknowledgementLabel={t("data.wipe.acknowledge")}
        onConfirm={() => void handleWipe()}
        onCancel={() => setWipeOpen(false)}
      />
    </div>
  );
}

/** Panel root: loads the picker catalogs once and lays out the two cards. */
export function DataManagementPanel() {
  const [sessions, setSessions] = useState<SessionHistoryItem[] | null>(null);
  const [resumes, setResumes] = useState<ResumeResponse[] | null>(null);
  const [reloadSeq, setReloadSeq] = useState(0);

  const activeLoadCleanup = useRef<(() => void) | null>(null);
  const mounted = useRef(false);

  const loadItems = useCallback(() => {
    activeLoadCleanup.current?.();
    if (!mounted.current) return;
    let alive = true;
    activeLoadCleanup.current = () => {
      alive = false;
    };
    const isAlive = () => alive;
    fetchPickerList(isAlive, () => recordsHttp.listSessions()).then(({ rows }) => {
      if (!alive) return;
      setSessions(rows);
    });
    fetchPickerList(isAlive, () => resumeHttp.listResumes()).then(({ rows }) => {
      if (!alive) return;
      setResumes(rows);
    });
    return activeLoadCleanup.current;
  }, []);

  useEffect(() => {
    mounted.current = true;
    loadItems();
    return () => {
      mounted.current = false;
      activeLoadCleanup.current?.();
    };
  }, [loadItems]);

  // A finished wipe bumps the sequence to refetch both catalogs: the pickers
  // then point at whatever actually survived (nothing).
  useEffect(() => {
    if (reloadSeq > 0) loadItems();
  }, [reloadSeq, loadItems]);

  // Null-safe list snapshots for the pickers.
  const sessionList = sessions ?? [];
  const resumeList = resumes ?? [];

  return (
    <div className="space-y-4">
      <ExportCard
        sessions={sessionList}
        resumes={resumeList}
        onExported={() => setReloadSeq((n) => n + 1)}
      />
      <WipeCard onWiped={() => setReloadSeq((n) => n + 1)} />
    </div>
  );
}
