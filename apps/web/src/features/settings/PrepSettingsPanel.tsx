"use client";

/**
 * @file PrepSettingsPanel.tsx
 * @description Interview-prep settings: ask-dialog timeout, empty-session purge,
 * plus the long-term memory manager below (one domain, one category).
 */

import { Eraser, GraduationCap, Shrink, Trash2 } from "lucide-react";
import { useState } from "react";
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
  MEMORY_INDEX_LIMIT_DEFAULT,
  readCompactDirective,
  readCompactIntensity,
  readCompactRetain,
  readCompactThreshold,
  readMemoryIndexLimit,
  writeCompactDirective,
  writeCompactIntensity,
  writeCompactRetain,
  writeCompactThreshold,
  writeMemoryIndexLimit,
  type CompactThresholdSetting,
  type CompactionIntensity,
} from "@/lib/compactThreshold";
import { DangerActionCard } from "./DangerActionCard";
import { MemoriesSettingsPanel } from "./MemoriesSettingsPanel";

export function PrepSettingsPanel() {
  const t = useT("settings");
  const [seconds, setSeconds] = useState<number>(() => readAskTimeoutSec());
  const [compactThreshold, setCompactThreshold] = useState<CompactThresholdSetting>(() =>
    readCompactThreshold(),
  );
  const [compactIntensity, setCompactIntensity] = useState<CompactionIntensity>(() =>
    readCompactIntensity(),
  );
  const [compactDirective, setCompactDirective] = useState<string>(() => readCompactDirective());
  const [compactRetain, setCompactRetain] = useState<number>(() => readCompactRetain());
  const [memoryIndexLimit, setMemoryIndexLimit] = useState<number>(() => readMemoryIndexLimit());

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

  // Thrown errors keep the DangerActionCard dialog open; the toast already fired.
  const handlePurge = async () => {
    try {
      const { deleted } = await prepCoachHttp.purgeEmptySessions();
      toast.success(t("prep.purge.done", { count: deleted }));
    } catch (err) {
      toast.error(err instanceof Error ? formatApiError(err) : t("prep.purge.failed"));
      throw err;
    }
  };

  const handlePurgeAll = async () => {
    try {
      const { deleted } = await prepCoachHttp.purgeAllSessions();
      toast.success(t("prep.purgeAll.done", { count: deleted }));
    } catch (err) {
      toast.error(err instanceof Error ? formatApiError(err) : t("prep.purgeAll.failed"));
      throw err;
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
          <GraduationCap size={16} className="text-[var(--primary)]" />
          <h2 className="text-[14px] font-semibold">{t("prep.memoryIndex.title")}</h2>
        </div>
        <p className="text-[13px] leading-relaxed text-ink-muted">{t("prep.memoryIndex.desc")}</p>
        <div className="mt-3 max-w-xs">
          <label
            htmlFor="prep-memory-index-limit"
            className="block text-[12px] font-medium text-ink-muted"
          >
            {t("prep.memoryIndex.label")}
          </label>
          <input
            id="prep-memory-index-limit"
            type="number"
            className="field-input !h-9 mt-1 w-28 text-[13px]"
            min={0}
            max={500}
            step={1}
            value={memoryIndexLimit}
            onChange={(e) => {
              const parsed = Number(e.target.value);
              if (Number.isInteger(parsed) && parsed >= 0 && parsed <= 500) {
                setMemoryIndexLimit(parsed);
                writeMemoryIndexLimit(parsed);
              }
            }}
          />
          <p className="mt-1 text-[11px] text-ink-subtle">
            {memoryIndexLimit === 0
              ? t("prep.memoryIndex.allHint")
              : t("prep.memoryIndex.defaultHint", { n: MEMORY_INDEX_LIMIT_DEFAULT })}
          </p>
        </div>
      </div>
      <DangerActionCard
        icon={<Eraser size={16} className="text-[var(--primary)]" />}
        title={t("prep.purge.title")}
        description={t("prep.purge.desc")}
        actionLabel={t("prep.purge.action")}
        confirmTitle={t("prep.purge.confirmTitle")}
        confirmBody={t("prep.purge.confirmBody")}
        onConfirm={() => handlePurge()}
      />
      <DangerActionCard
        icon={<Trash2 size={16} className="text-[var(--danger)]" />}
        title={t("prep.purgeAll.title")}
        description={t("prep.purgeAll.desc")}
        actionLabel={t("prep.purgeAll.action")}
        confirmTitle={t("prep.purgeAll.confirmTitle")}
        confirmBody={t("prep.purgeAll.confirmBody")}
        onConfirm={() => handlePurgeAll()}
      />
      <MemoriesSettingsPanel />
    </div>
  );
}
