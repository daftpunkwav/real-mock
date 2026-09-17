"use client";

/**
 * @file PrepSettingsPanel.tsx
 * @description Interview-prep settings: ask-dialog timeout, empty-session purge,
 * plus the long-term memory manager below (one domain, one category).
 */

import { Eraser, GraduationCap, Shrink, Trash2 } from "lucide-react";
import { useState } from "react";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Select } from "@/components/Select";
import { toast } from "@/components/Toast";
import { useT } from "@/i18n";
import { prepCoachHttp } from "@/lib/api/clients";
import { formatApiError } from "@/lib/api/base";
import {
  ASK_TIMEOUT_DEFAULT_SEC,
  ASK_TIMEOUT_OPTIONS,
  readAskTimeoutSec,
  writeAskTimeoutSec,
} from "@/lib/askTimeout";
import {
  COMPACT_DIRECTIVE_MAX_CHARS,
  COMPACT_INTENSITY_DEFAULT,
  COMPACT_INTENSITY_OPTIONS,
  COMPACT_RETAIN_DEFAULT,
  COMPACT_RETAIN_MAX,
  COMPACT_RETAIN_MIN,
  COMPACT_THRESHOLD_DEFAULT,
  COMPACT_THRESHOLD_OPTIONS,
  readCompactDirective,
  readCompactIntensity,
  readCompactRetain,
  readCompactThreshold,
  writeCompactDirective,
  writeCompactIntensity,
  writeCompactRetain,
  writeCompactThreshold,
  type CompactThresholdSetting,
  type CompactionIntensity,
} from "@/lib/compactThreshold";
import { MemoriesSettingsPanel } from "./MemoriesSettingsPanel";

export function PrepSettingsPanel() {
  const t = useT("settings");
  const tc = useT("common");
  const [seconds, setSeconds] = useState<number>(() => readAskTimeoutSec());
  const [compactThreshold, setCompactThreshold] = useState<CompactThresholdSetting>(
    () => readCompactThreshold(),
  );
  const [compactIntensity, setCompactIntensity] = useState<CompactionIntensity>(() =>
    readCompactIntensity(),
  );
  const [compactDirective, setCompactDirective] = useState<string>(() => readCompactDirective());
  const [compactRetain, setCompactRetain] = useState<number>(() => readCompactRetain());
  const [confirmingPurge, setConfirmingPurge] = useState(false);
  const [purging, setPurging] = useState(false);
  const [confirmingPurgeAll, setConfirmingPurgeAll] = useState(false);
  const [purgingAll, setPurgingAll] = useState(false);

  const change = (next: number) => {
    const valid = ASK_TIMEOUT_OPTIONS.includes(next) ? next : ASK_TIMEOUT_DEFAULT_SEC;
    setSeconds(valid);
    writeAskTimeoutSec(valid);
  };

  const changeCompactThreshold = (next: CompactThresholdSetting) => {
    const valid = (COMPACT_THRESHOLD_OPTIONS as (string | number)[]).includes(next)
      ? next
      : COMPACT_THRESHOLD_DEFAULT;
    setCompactThreshold(valid);
    writeCompactThreshold(valid);
  };

  const intensityLabels: Record<CompactionIntensity, string> = {
    light: t("prep.compact.intensityLight"),
    balanced: t("prep.compact.intensityBalanced"),
    aggressive: t("prep.compact.intensityAggressive"),
  };

  const changeCompactIntensity = (next: CompactionIntensity) => {
    const valid = (COMPACT_INTENSITY_OPTIONS as string[]).includes(next)
      ? next
      : COMPACT_INTENSITY_DEFAULT;
    setCompactIntensity(valid);
    writeCompactIntensity(valid);
  };

  const changeCompactDirective = (next: string) => {
    const valid = (next ?? "").slice(0, COMPACT_DIRECTIVE_MAX_CHARS);
    setCompactDirective(valid);
    writeCompactDirective(valid);
  };

  const changeCompactRetain = (raw: string) => {
    // Non-negative integer only: negatives and garbage fall back instead of
    // widening or disabling compaction silently (backend rejects too).
    const parsed = Number(raw);
    const valid =
      raw.trim() !== "" && Number.isInteger(parsed) && parsed >= COMPACT_RETAIN_MIN
        ? Math.min(parsed, COMPACT_RETAIN_MAX)
        : COMPACT_RETAIN_DEFAULT;
    setCompactRetain(valid);
    writeCompactRetain(valid);
  };

  const handlePurge = async () => {
    setPurging(true);
    try {
      const { deleted } = await prepCoachHttp.purgeEmptySessions();
      toast.success(t("prep.purge.done", { count: deleted }));
      setConfirmingPurge(false);
    } catch (err) {
      toast.error(err instanceof Error ? formatApiError(err) : t("prep.purge.failed"));
      throw err;
    } finally {
      setPurging(false);
    }
  };

  const handlePurgeAll = async () => {
    setPurgingAll(true);
    try {
      const { deleted } = await prepCoachHttp.purgeAllSessions();
      toast.success(t("prep.purgeAll.done", { count: deleted }));
      setConfirmingPurgeAll(false);
    } catch (err) {
      toast.error(err instanceof Error ? formatApiError(err) : t("prep.purgeAll.failed"));
      throw err;
    } finally {
      setPurgingAll(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="surface-card p-4">
        <div className="mb-1 flex items-center gap-2">
          <GraduationCap size={16} className="text-[var(--primary)]" />
          <h2 className="text-[14px] font-semibold">{t("prep.timeout.title")}</h2>
        </div>
        <p className="text-[13px] leading-relaxed text-ink-muted">{t("prep.timeout.desc")}</p>
        <div className="mt-3 max-w-xs">
          <span className="block text-[12px] font-medium text-ink-muted">
            {t("prep.timeout.label")}
          </span>
          <Select
            className="mt-1"
            ariaLabel={t("prep.timeout.label")}
            value={seconds}
            options={ASK_TIMEOUT_OPTIONS.map((option) => ({
              value: option,
              label:
                option === 0
                  ? t("prep.timeout.off")
                  : t("prep.timeout.minutes", { n: option / 60 }),
            }))}
            onChange={change}
          />
        </div>
      </div>
      <div className="surface-card p-4">
        <div className="mb-1 flex items-center gap-2">
          <Shrink size={16} className="text-[var(--primary)]" />
          <h2 className="text-[14px] font-semibold">{t("prep.compact.title")}</h2>
        </div>
        <p className="text-[13px] leading-relaxed text-ink-muted">{t("prep.compact.desc")}</p>
        <div className="mt-3 grid max-w-xs gap-3">
          <div>
            <span className="block text-[12px] font-medium text-ink-muted">
              {t("prep.compact.label")}
            </span>
            <Select
              className="mt-1"
              ariaLabel={t("prep.compact.label")}
              value={compactThreshold}
              options={COMPACT_THRESHOLD_OPTIONS.map((option) => ({
                value: option,
                label:
                  option === "auto"
                    ? t("prep.compact.auto")
                    : t("prep.compact.percent", { n: Math.round(option * 100) }),
              }))}
              onChange={changeCompactThreshold}
            />
          </div>
          <div>
            <span className="block text-[12px] font-medium text-ink-muted">
              {t("prep.compact.intensityLabel")}
            </span>
            <Select
              className="mt-1"
              ariaLabel={t("prep.compact.intensityLabel")}
              value={compactIntensity}
              options={COMPACT_INTENSITY_OPTIONS.map((option) => ({
                value: option,
                label: intensityLabels[option],
              }))}
              onChange={changeCompactIntensity}
            />
          </div>
          <div>
            <label
              htmlFor="prep-compact-directive"
              className="block text-[12px] font-medium text-ink-muted"
            >
              {t("prep.compact.directiveLabel")}
            </label>
            <textarea
              id="prep-compact-directive"
              className="field-textarea mt-1 min-h-16 w-full text-[13px]"
              rows={2}
              maxLength={COMPACT_DIRECTIVE_MAX_CHARS}
              placeholder={t("prep.compact.directivePlaceholder")}
              value={compactDirective}
              onChange={(e) => changeCompactDirective(e.target.value)}
            />
          </div>
          <div>
            <label
              htmlFor="prep-compact-retain"
              className="block text-[12px] font-medium text-ink-muted"
            >
              {t("prep.compact.retainLabel")}
            </label>
            <input
              id="prep-compact-retain"
              type="number"
              className="field-input !h-9 mt-1 w-28 text-[13px]"
              min={COMPACT_RETAIN_MIN}
              max={COMPACT_RETAIN_MAX}
              step={1}
              value={compactRetain}
              onChange={(e) => changeCompactRetain(e.target.value)}
            />
          </div>
        </div>
      </div>
      <div className="surface-card p-4">
        <div className="mb-1 flex items-center gap-2">
          <Eraser size={16} className="text-[var(--primary)]" />
          <h2 className="text-[14px] font-semibold">{t("prep.purge.title")}</h2>
        </div>
        <p className="text-[13px] leading-relaxed text-ink-muted">{t("prep.purge.desc")}</p>
        <button
          type="button"
          onClick={() => setConfirmingPurge(true)}
          disabled={purging}
          className="btn-secondary mt-3 text-[13px] disabled:cursor-not-allowed disabled:opacity-45"
        >
          {t("prep.purge.action")}
        </button>
      </div>
      <div className="surface-card p-4">
        <div className="mb-1 flex items-center gap-2">
          <Trash2 size={16} className="text-[var(--danger)]" />
          <h2 className="text-[14px] font-semibold">{t("prep.purgeAll.title")}</h2>
        </div>
        <p className="text-[13px] leading-relaxed text-ink-muted">{t("prep.purgeAll.desc")}</p>
        <button
          type="button"
          onClick={() => setConfirmingPurgeAll(true)}
          disabled={purgingAll}
          className="btn-danger mt-3 text-[13px] disabled:cursor-not-allowed disabled:opacity-45"
        >
          {t("prep.purgeAll.action")}
        </button>
      </div>
      <MemoriesSettingsPanel />
      <ConfirmDialog
        open={confirmingPurge}
        title={t("prep.purge.confirmTitle")}
        message={t("prep.purge.confirmBody")}
        confirmLabel={t("prep.purge.action")}
        cancelLabel={tc("confirm.cancel")}
        busy={purging}
        onConfirm={() => void handlePurge()}
        onCancel={() => setConfirmingPurge(false)}
      />
      <ConfirmDialog
        open={confirmingPurgeAll}
        title={t("prep.purgeAll.confirmTitle")}
        message={t("prep.purgeAll.confirmBody")}
        confirmLabel={t("prep.purgeAll.action")}
        cancelLabel={tc("confirm.cancel")}
        busy={purgingAll}
        onConfirm={() => void handlePurgeAll()}
        onCancel={() => setConfirmingPurgeAll(false)}
      />
    </div>
  );
}
