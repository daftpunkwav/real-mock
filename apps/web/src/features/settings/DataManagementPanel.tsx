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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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

export function DataManagementPanel() {
  const t = useT("settings");
  const tc = useT("common");
  const [kind, setKind] = useState<ExportKind>("report");
  const [format, setFormat] = useState<ExportFormat>("md");
  const [sessions, setSessions] = useState<SessionHistoryItem[] | null>(null);
  const [resumes, setResumes] = useState<ResumeResponse[] | null>(null);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [resumeId, setResumeId] = useState<number | null>(null);
  const [includeResume, setIncludeResume] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [wipeOpen, setWipeOpen] = useState(false);
  const [wiping, setWiping] = useState(false);

  const activeLoadCleanup = useRef<(() => void) | null>(null);
  const mounted = useRef(false);

  const loadItems = useCallback(() => {
    activeLoadCleanup.current?.();
    if (!mounted.current) return;
    let alive = true;
    activeLoadCleanup.current = () => {
      alive = false;
    };
    recordsHttp
      .listSessions()
      .then((rows) => {
        if (!alive) return;
        const list = Array.isArray(rows) ? rows : [];
        setSessions(list);
        setSessionId(list[0]?.id ?? null);
      })
      .catch(() => {
        if (alive) setSessions([]);
      });
    resumeHttp
      .listResumes()
      .then((rows) => {
        if (!alive) return;
        const list = Array.isArray(rows) ? rows : [];
        setResumes(list);
        setResumeId(list[0]?.id ?? null);
      })
      .catch(() => {
        if (alive) setResumes([]);
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

  const sessionsReady = sessions !== null;
  const resumesReady = resumes !== null;
  // Null-safe list snapshots for JSX and the export handler (Codacy flags `!`).
  const sessionList = sessions ?? [];
  const resumeList = resumes ?? [];
  const itemReady =
    kind === "analysis" ? resumesReady && resumeId != null : sessionsReady && sessionId != null;

  const sessionLabel = useCallback((s: SessionHistoryItem) => {
    const date = (s.created_at || s.started_at || "").slice(0, 10);
    const who = [s.role, s.company].filter(Boolean).join(" · ");
    return `#${s.id}${who ? ` ${who}` : ""}${date ? ` ${date}` : ""}`;
  }, []);

  const handleExport = async () => {
    if (exporting) return;
    setExporting(true);
    try {
      let file: { filename: string; content: string; mime: string };
      if (kind === "analysis") {
        const rid = resumeId;
        if (rid == null) return;
        file = await resumeHttp.exportAnalysis(rid, format, includeResume);
      } else {
        const sid = sessionId;
        if (sid == null) return;
        file =
          kind === "report"
            ? await recordsHttp.exportReport(sid, format)
            : await recordsHttp.exportRecord(sid, format);
      }
      downloadTextFile(file.filename, file.content, file.mime);
      toast.success(t("data.export.done", { name: file.filename }));
    } catch (err) {
      toast.error(err instanceof Error ? formatApiError(err) : t("data.export.failed"));
    } finally {
      setExporting(false);
    }
  };

  const handleWipe = async () => {
    setWiping(true);
    try {
      await settingsHttp.clearAllData();
      toast.success(t("data.wipe.done"));
      setWiping(false);
      setWipeOpen(false);
      // The pickers now point at deleted rows: refetch so a follow-up export
      // selects from what actually exists.
      loadItems();
    } catch (err) {
      toast.error(err instanceof Error ? formatApiError(err) : t("data.wipe.failed"));
    } finally {
      setWiping(false);
    }
  };

  const kindOptions = useMemo(
    () => [
      { value: "report" as const, label: t("data.export.kindReport") },
      { value: "record" as const, label: t("data.export.kindRecord") },
      { value: "analysis" as const, label: t("data.export.kindAnalysis") },
    ],
    [t],
  );

  return (
    <div className="space-y-4">
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
              {kindOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </FieldRow>

          {kind !== "analysis" ? (
            <FieldRow label={t("data.export.item")}>
              <select
                className="field-select !h-9 !text-[13px] disabled:opacity-60"
                value={sessionId ?? ""}
                disabled={sessionList.length === 0}
                onChange={(e) => {
                  setSessionId(e.target.value ? Number(e.target.value) : null);
                }}
              >
                {sessionList.length === 0 ? (
                  <option value="">{t("data.export.noSessions")}</option>
                ) : (
                  sessionList.map((s) => (
                    <option key={s.id} value={s.id}>
                      {sessionLabel(s)}
                    </option>
                  ))
                )}
              </select>
            </FieldRow>
          ) : (
            <>
              <FieldRow label={t("data.export.item")}>
                <select
                  className="field-select !h-9 !text-[13px] disabled:opacity-60"
                  value={resumeId ?? ""}
                  disabled={resumeList.length === 0}
                  onChange={(e) => {
                    setResumeId(e.target.value ? Number(e.target.value) : null);
                  }}
                >
                  {resumeList.length === 0 ? (
                    <option value="">{t("data.export.noResumes")}</option>
                  ) : (
                    resumeList.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.filename}
                      </option>
                    ))
                  )}
                </select>
              </FieldRow>
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
            </>
          )}

          <FieldRow label={t("data.export.format")}>
            <div className="flex gap-1.5">
              {(["md", "json"] as const).map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => {
                    setFormat(f);
                  }}
                  aria-pressed={format === f}
                  className={`rounded-md border px-3 py-1.5 text-[12px] font-medium transition-colors ${
                    format === f
                      ? "border-[var(--primary)] bg-[var(--info-soft)] text-ink"
                      : "border-surface-border text-ink-muted hover:border-[var(--primary)] hover:text-ink"
                  }`}
                >
                  {f === "md" ? t("data.export.formatMd") : t("data.export.formatJson")}
                </button>
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
    </div>
  );
}
