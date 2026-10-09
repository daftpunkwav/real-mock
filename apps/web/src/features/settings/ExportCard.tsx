"use client";

/**
 * @file ExportCard.tsx
 * @description Data export card: pick the data kind (report / record /
 * analysis), the item, and the format; the download streams through the shared
 * downloadTextFile helper.
 */

import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import { Spinner } from "@/components/Spinner";
import { toast } from "@/components/Toast";
import { useT } from "@/i18n";
import { downloadTextFile } from "@/lib/download";
import { formatApiError } from "@/lib/api/base";
import { recordsHttp, resumeHttp } from "@/lib/api/clients";
import type { ResumeResponse } from "@/lib/api/contract";
import type { SessionHistoryItem } from "@/types/domains/records";

type ExportKind = "report" | "record" | "analysis";
type ExportFormat = "md" | "json";

/** Item picker row shared by the kind-dependent selects. */
const FieldRow = ({ label, children }: { label: string; children: React.ReactNode }) => {
  return (
    <div className="grid grid-cols-[96px_minmax(0,1fr)] items-center gap-2 sm:grid-cols-[120px_minmax(0,1fr)]">
      <span className="text-[12px] text-ink-subtle">{label}</span>
      {children}
    </div>
  );
};

/** Label shown for one session row in the item picker. */
const sessionLabel = (s: SessionHistoryItem): string => {
  const date = (s.created_at || s.started_at || "").slice(0, 10);
  const who = [s.role, s.company].filter(Boolean).join(" · ");
  return `#${s.id}${who ? ` ${who}` : ""}${date ? ` ${date}` : ""}`;
};

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
const PickerOption = ({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) => {
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
};

/** One option row of a picker select (or a placeholder when empty). */
const PickerSelect = <T extends { id: number }>({
  value,
  items,
  disabled,
  emptyLabel,
  renderLabel,
  onChange,
}: {
  value: number | null;
  items: T[];
  disabled: boolean;
  emptyLabel: string;
  renderLabel: (item: T) => string;
  onChange: (id: number | null) => void;
}) => {
  const t = useT("settings");
  return (
    <FieldRow label={t("data.export.item")}>
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
};

/** Arguments identifying one export the user asked for. */
interface ExportRequest {
  kind: ExportKind;
  format: ExportFormat;
  sessionId: number | null;
  resumeId: number | null;
  includeResume: boolean;
}

/** Fetch the export file for one request, or null when its item is unset. */
const requestExportFile = async (req: ExportRequest) => {
  if (req.kind === "analysis") {
    if (req.resumeId == null) return null;
    return resumeHttp.exportAnalysis(req.resumeId, req.format, req.includeResume);
  }
  if (req.sessionId == null) return null;
  return req.kind === "report"
    ? recordsHttp.exportReport(req.sessionId, req.format)
    : recordsHttp.exportRecord(req.sessionId, req.format);
};

/** Export card: kind/item/format pickers plus the download action. */
export const ExportCard = ({
  sessions,
  resumes,
  onExported,
}: {
  sessions: SessionHistoryItem[];
  resumes: ResumeResponse[];
  onExported: () => void;
}) => {
  const t = useT("settings");
  const [kind, setKind] = useState<ExportKind>("report");
  const [format, setFormat] = useState<ExportFormat>("md");
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [resumeId, setResumeId] = useState<number | null>(null);
  const [includeResume, setIncludeResume] = useState(false);
  const [exporting, setExporting] = useState(false);

  const isAnalysis = kind === "analysis";
  const itemReady = isAnalysis ? resumeId != null : sessionId != null;

  // Preselect the first row and re-point at a live row after reloads: a
  // select whose value matches no option renders as blank, and picking the
  // shown item would not fire onChange — with one item the export button
  // could never be enabled, and a wiped-away id would silently unselect.
  useEffect(() => {
    if (isAnalysis) {
      if (resumeId == null || !resumes.some((r) => r.id === resumeId)) {
        setResumeId(resumes[0]?.id ?? null);
      }
    } else if (sessionId == null || !sessions.some((s) => s.id === sessionId)) {
      setSessionId(sessions[0]?.id ?? null);
    }
  }, [isAnalysis, resumeId, resumes, sessionId, sessions]);

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
          <PickerSelect
            value={resumeId}
            items={resumes}
            disabled={resumes.length === 0}
            emptyLabel={t("data.export.noResumes")}
            renderLabel={(r) => r.filename}
            onChange={setResumeId}
          />
        ) : (
          <PickerSelect
            value={sessionId}
            items={sessions}
            disabled={sessions.length === 0}
            emptyLabel={t("data.export.noSessions")}
            renderLabel={sessionLabel}
            onChange={setSessionId}
          />
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
};
