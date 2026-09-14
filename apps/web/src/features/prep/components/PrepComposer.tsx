"use client";

/** Prep composer: input, token gauge, model/effort selectors, and send. */

import { Check, ChevronDown, ChevronRight, Hash, Send, Square, X } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { useT, type MessageKey } from "@/i18n";
import { ContextGauge, EffortSelect, ModelSelect, formatTokens } from "@/components/ModelControls";
import type { PrepSessionSummary } from "@/lib/api/contract";
import type { ModelProfile, PrepUsageStats, ReasoningEffort } from "@/types";
import { estimatePrepContext } from "../contextEstimate";
import { resolveSelectedModel } from "../modelChoice";
import {
  detectHashQuery,
  refCandidates,
  stripHashQuery,
  type PendingSessionRef,
} from "../sessionRefs";
import { matchSlashCommands, parseSlashCommand, resolveSlashCommand, type SlashName } from "../slashCommands";
import type { PrepChatMessage } from "../types";

interface PrepComposerProps {
  messages: PrepChatMessage[];
  tokenUsage: number;
  usage: PrepUsageStats | null;
  /** Backend-measured context buckets by stable key (null until first fetch). */
  contextBuckets: Record<string, number> | null;
  contextTotal: number;
  /** Latest turn's mechanical input estimate (display fallback only). */
  estimatedPrompt: number;
  chatModels: ModelProfile[];
  selectedModelId: number | null;
  onModelChange: (id: number | null) => void;
  defaultChatProfile: ModelProfile | null;
  effort: ReasoningEffort;
  onEffortChange: (e: ReasoningEffort) => void;
  loading: boolean;
  /** True while a manual compaction is in flight (send blocked, progress shown). */
  compacting?: boolean;
  input: string;
  onInputChange: (v: string) => void;
  onSend: () => void;
  onStop: () => void;
  /** Execute a slash command instead of sending (input cleared by the handler). */
  onSlashCommand: (name: SlashName, args: string) => void;
  /** Sessions available for "#" references. */
  sessions: PrepSessionSummary[];
  currentSessionId: number | null;
  /** Session chips attached to the next send (per-turn references). */
  pendingRefs: PendingSessionRef[];
  onAddRef: (ref: PendingSessionRef) => void;
  onRemoveRef: (id: number) => void;
}

/**
 * Model selector grouped by provider: cascading two-level menu
 * (provider list on the left, its models on the right).
 * Groups by ModelProfile.provider_name, which already ships on every chat
 * model item — no data is invented. Falls back to the flat ModelSelect when
 * grouping data is absent (any model lacks a provider name) or when fewer
 * than two providers make a cascade pointless. Selection and
 * default-profile semantics mirror ModelSelect exactly (null follows the
 * default profile when it is listed).
 */
function GroupedModelSelect({
  models,
  value,
  onChange,
  ariaLabel,
  defaultProfile,
}: {
  models: ModelProfile[];
  value: number | null;
  onChange: (id: number | null) => void;
  ariaLabel: string;
  defaultProfile?: ModelProfile | null;
}) {
  const t = useT("common");
  const [open, setOpen] = useState(false);
  const [activeProvider, setActiveProvider] = useState("");
  const listId = useId();

  // Provider groups in first-appearance order; models keep backend order.
  const groups = useMemo(() => {
    const order: string[] = [];
    const byProvider = new Map<string, ModelProfile[]>();
    for (const m of models) {
      const provider = (m.provider_name ?? "").trim();
      if (!provider) return [];
      if (!byProvider.has(provider)) {
        byProvider.set(provider, []);
        order.push(provider);
      }
      byProvider.get(provider)?.push(m);
    }
    return order.map((provider) => ({
      provider,
      models: byProvider.get(provider) ?? [],
    }));
  }, [models]);
  const hasGrouping = groups.length >= 2;

  // Identical to ModelSelect: null follows the default profile when listed.
  const effectiveValue =
    value ?? (defaultProfile && models.some((m) => m.id === defaultProfile.id) ? defaultProfile.id : "");
  const selected = models.find((m) => m.id === effectiveValue) ?? null;
  const selectedProvider = (selected?.provider_name ?? "").trim();
  const activeModels = groups.find((g) => g.provider === activeProvider)?.models ?? [];
  // Window suffix: the effective context window travels with the label so a
  // mismatch between the configured value and the runtime budget is visible.
  const labelWithWindow = (m: ModelProfile) =>
    m.context_window > 0 ? `${m.label} · ${formatTokens(m.context_window)}` : m.label;

  if (!hasGrouping) {
    return (
      <ModelSelect
        models={models}
        value={value}
        onChange={onChange}
        ariaLabel={ariaLabel}
        defaultProfile={defaultProfile}
      />
    );
  }

  const openMenu = () => {
    setActiveProvider(selectedProvider || groups[0]?.provider || "");
    setOpen(true);
  };

  return (
    <div className="relative min-w-0 shrink-0">
      <button
        type="button"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={ariaLabel}
        onClick={() => (open ? setOpen(false) : openMenu())}
        onKeyDown={(e) => {
          if (e.key === "Escape" && open) {
            e.preventDefault();
            setOpen(false);
          }
        }}
        className="flex h-7 w-auto min-w-0 max-w-[220px] items-center justify-between gap-1.5 rounded-md bg-transparent px-1.5 text-[12px] text-ink transition-colors hover:bg-surface-muted focus:outline-none focus-visible:bg-surface-muted"
      >
        <span className="flex min-w-0 flex-1 items-baseline gap-1.5" title={selected ? labelWithWindow(selected) : undefined}>
          <span className="min-w-0 flex-1 truncate">
            {selected?.label ?? (!defaultProfile ? t("model.notSet") : "")}
          </span>
          {selected && selected.context_window > 0 ? (
            <span className="shrink-0 text-[10px] text-ink-subtle">{formatTokens(selected.context_window)}</span>
          ) : null}
        </span>
        <ChevronDown size={14} className="shrink-0 text-ink-subtle" />
      </button>
      {open && (
        <>
          {/* Click outside the menu to close */}
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} aria-hidden />
          <div
            role="listbox"
            id={listId}
            aria-label={ariaLabel}
            className="surface-card absolute bottom-full right-0 z-40 mb-2 flex max-h-64 w-[380px] max-w-[calc(100vw-2rem)] overflow-hidden !p-1 shadow-lg"
          >
            {/* Provider list: hover or click drives the model column. */}
            <div className="w-36 shrink-0 overflow-y-auto border-r border-surface-border p-1">
              {groups.map((g) => {
                const focused = g.provider === activeProvider;
                return (
                  <button
                    key={g.provider}
                    type="button"
                    role="menuitem"
                    aria-label={g.provider}
                    onMouseEnter={() => setActiveProvider(g.provider)}
                    onClick={() => setActiveProvider(g.provider)}
                    className={`flex w-full items-center gap-1 rounded-md px-2.5 py-2 text-left text-[12px] transition-colors ${
                      focused ? "bg-surface-muted font-medium text-ink" : "text-ink-muted"
                    }`}
                  >
                    <span className="min-w-0 flex-1 truncate">{g.provider}</span>
                    <ChevronRight size={13} className="shrink-0 text-ink-subtle" />
                  </button>
                );
              })}
            </div>
            {/* Models of the active provider. */}
            <div className="min-w-0 flex-1 overflow-y-auto p-1">
              {!defaultProfile && (
                <button
                  key="__unset"
                  type="button"
                  role="option"
                  aria-selected={effectiveValue === ""}
                  onClick={() => {
                    onChange(null);
                    setOpen(false);
                  }}
                  className={`flex h-9 w-full cursor-pointer items-center justify-between gap-2 rounded-md px-2.5 text-left text-[13px] transition-colors ${
                    effectiveValue === ""
                      ? "bg-surface-muted font-medium text-[var(--primary)]"
                      : "text-ink hover:bg-surface-muted"
                  }`}
                >
                  <span className="min-w-0 truncate">{t("model.notSet")}</span>
                  {effectiveValue === "" && <Check size={14} className="shrink-0" />}
                </button>
              )}
              {activeModels.map((m) => {
                const active = m.id === effectiveValue;
                return (
                  <button
                    key={m.id}
                    type="button"
                    role="option"
                    aria-selected={active}
                    onClick={() => {
                      onChange(m.id);
                      setOpen(false);
                    }}
                    title={labelWithWindow(m)}
                    className={`flex h-9 w-full cursor-pointer items-center justify-between gap-2 rounded-md px-2.5 text-left text-[13px] transition-colors ${
                      active
                        ? "bg-surface-muted font-medium text-[var(--primary)]"
                        : "text-ink hover:bg-surface-muted"
                    }`}
                  >
                    <span className="min-w-0 truncate">{labelWithWindow(m)}</span>
                    {active && <Check size={14} className="shrink-0" />}
                  </button>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/** Backend bucket keys in panel order with stable colors. */
const BUCKET_ORDER: { key: string; color: string; label: MessageKey<"common">; hint: MessageKey<"common"> }[] = [
  { key: "user", color: "var(--primary)", label: "context.bucket.user", hint: "context.bucket.userHint" },
  { key: "assistant", color: "#8b5cf6", label: "context.bucket.assistant", hint: "context.bucket.assistantHint" },
  { key: "thinking", color: "#f59e0b", label: "context.bucket.thinking", hint: "context.bucket.thinkingHint" },
  { key: "tools", color: "#22c55e", label: "context.bucket.tools", hint: "context.bucket.toolsHint" },
  { key: "system", color: "#94a3b8", label: "context.bucket.system", hint: "context.bucket.systemHint" },
  { key: "memory", color: "#ec4899", label: "context.bucket.memory", hint: "context.bucket.memoryHint" },
  { key: "other", color: "#64748b", label: "context.bucket.other", hint: "context.bucket.otherHint" },
];

export function PrepComposer({
  messages,
  tokenUsage,
  usage,
  contextBuckets,
  contextTotal,
  estimatedPrompt,
  chatModels,
  selectedModelId,
  onModelChange,
  defaultChatProfile,
  effort,
  onEffortChange,
  loading,
  compacting = false,
  input,
  onInputChange,
  onSend,
  onStop,
  onSlashCommand,
  sessions,
  currentSessionId,
  pendingRefs,
  onAddRef,
  onRemoveRef,
}: PrepComposerProps) {
  const t = useT("prep");
  const tc = useT("common");
  const selectedModel = resolveSelectedModel(
    chatModels,
    selectedModelId,
    defaultChatProfile,
  );
  const win = selectedModel?.context_window || 0;
  // Local fallback estimate (no reasoning/tool split for server-side blocks).
  const est = estimatePrepContext(messages, tokenUsage);
  // Backend-measured buckets win; hide exact-zero rows to cut noise.
  const breakdown = contextBuckets
    ? BUCKET_ORDER.map((b) => ({
        label: tc(b.label),
        hint: tc(b.hint),
        value: contextBuckets[b.key] ?? 0,
        color: b.color,
      })).filter((b) => b.value > 0)
    : [
        { label: t("tokens.gauge.messages"), value: est.userEst, color: "var(--primary)" },
        { label: t("tokens.gauge.replies"), value: est.assistantEst, color: "#8b5cf6" },
        { label: t("tokens.gauge.system"), value: est.systemEst, color: "#94a3b8" },
      ];
  const used = Math.max(est.used, contextTotal || 0, tokenUsage || 0);
  // Mechanical input fallback when the provider reported no prompt usage.
  const estimated = Math.max(estimatedPrompt || 0, contextTotal || 0, Math.round(est.measuredTotal));

  // Slash-command menu: typing "/" filters; Enter runs the highlight.
  const slashParsed = useMemo(() => parseSlashCommand(input), [input]);
  const slashMatches = useMemo(
    () => (slashParsed ? matchSlashCommands(slashParsed.name) : []),
    [slashParsed],
  );
  const [slashHighlight, setSlashHighlight] = useState(0);
  const runSlash = (name: SlashName) => {
    setSlashHighlight(0);
    onSlashCommand(name, slashParsed?.args ?? "");
  };
  const slashDesc: Record<SlashName, MessageKey<"prep">> = {
    compact: "slash.compactDesc",
    clear: "slash.clearDesc",
    help: "slash.helpDesc",
  };

  // Multiline input: single-line <input> drops pasted newlines (tables arrive
  // as one line), so this is an auto-growing textarea. Enter sends,
  // Shift+Enter inserts a newline; IME composition Enter never sends.
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const autoresize = useCallback(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, []);
  useEffect(() => {
    autoresize();
  }, [input, autoresize]);

  // "#" session references: trailing "#query" opens the session menu and wins
  // over the slash menu (the "#" was typed most recently).
  const hashQuery = useMemo(() => detectHashQuery(input), [input]);
  const pickedIds = useMemo(() => pendingRefs.map((r) => r.id), [pendingRefs]);
  const hashCandidates = useMemo(
    () =>
      hashQuery
        ? refCandidates(sessions, currentSessionId, pickedIds, hashQuery.query, t("sessions.newSessionFallback"))
        : [],
    [hashQuery, sessions, currentSessionId, pickedIds, t],
  );
  const [hashHighlight, setHashHighlight] = useState(0);
  const hashOpen = hashQuery !== null;
  const pickRef = (ref: PendingSessionRef) => {
    onAddRef(ref);
    onInputChange(stripHashQuery(input));
    setHashHighlight(0);
  };

  const menuOpen = hashOpen || (slashParsed !== null && slashMatches.length > 0);

  return (
    <div className="mt-3 flex shrink-0 flex-col gap-2">
      {pendingRefs.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5" aria-label={t("composer.refChips")}>
          {pendingRefs.map((ref) => (
            <span
              key={ref.id}
              className="flex max-w-[220px] items-center gap-1 rounded-full border border-[var(--primary)] bg-[var(--info-soft)] px-2 py-0.5 text-[11px] text-ink"
            >
              <Hash size={11} className="shrink-0 text-[var(--primary)]" />
              <span className="truncate">{ref.label}</span>
              <button
                type="button"
                onClick={() => onRemoveRef(ref.id)}
                className="shrink-0 rounded-full p-0.5 text-ink-subtle transition-colors hover:text-ink"
                aria-label={`${t("composer.refRemove")}: ${ref.label}`}
              >
                <X size={11} />
              </button>
            </span>
          ))}
        </div>
      )}
      {/* Single-box composer: textarea left, controls rail right. The
          container keeps a neutral border in every state (no accent ring),
          and the rail holds context gauge, model, effort, and send in one
          column so the input row stays a calm two lines. */}
      <div className="surface-card relative !rounded-2xl p-2 transition-colors">
        {hashOpen && (
          <div
            role="listbox"
            aria-label={t("composer.refMenuTitle")}
            className="surface-card absolute bottom-full left-0 z-40 mb-2 max-h-64 w-80 overflow-y-auto !p-1 shadow-lg"
          >
            {hashCandidates.length === 0 ? (
              <p className="px-2.5 py-2 text-[12px] text-ink-subtle">{t("composer.refMenuEmpty")}</p>
            ) : (
              hashCandidates.map((candidate, i) => (
                <button
                  key={candidate.id}
                  type="button"
                  role="option"
                  aria-selected={i === hashHighlight}
                  onMouseDown={(e) => {
                    // Beat input blur so the click lands before the menu closes.
                    e.preventDefault();
                    pickRef(candidate);
                  }}
                  onMouseEnter={() => setHashHighlight(i)}
                  className={`flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-[12px] transition-colors ${
                    i === hashHighlight ? "bg-surface-muted text-ink" : "text-ink-muted"
                  }`}
                >
                  <Hash size={12} className="shrink-0 text-[var(--primary)]" />
                  <span className="truncate">{candidate.label}</span>
                </button>
              ))
            )}
          </div>
        )}
        {!hashOpen && slashParsed !== null && slashMatches.length > 0 && (
          <div
            role="listbox"
            aria-label="/"
            className="surface-card absolute bottom-full left-0 z-40 mb-2 w-72 !p-1 shadow-lg"
          >
            {slashMatches.map((name, i) => (
              <button
                key={name}
                type="button"
                role="option"
                aria-selected={i === slashHighlight}
                onMouseDown={(e) => {
                  // Beat input blur so the click lands before the menu closes.
                  e.preventDefault();
                  runSlash(name);
                }}
                onMouseEnter={() => setSlashHighlight(i)}
                className={`flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-[12px] transition-colors ${
                  i === slashHighlight ? "bg-surface-muted text-ink" : "text-ink-muted"
                }`}
              >
                <span className="font-mono font-medium text-[var(--primary)]">/{name}</span>
                <span className="truncate">{t(slashDesc[name])}</span>
              </button>
            ))}
          </div>
        )}
        <textarea
          ref={inputRef}
          rows={2}
          className="prep-composer-input max-h-[160px] min-h-[54px] w-full resize-none overflow-y-auto bg-transparent px-2 py-1.5 text-sm leading-relaxed text-ink placeholder:text-ink-subtle focus:outline-none"
          title={t("composer.multilineHint")}
          value={input}
          onChange={(e) => {
            onInputChange(e.target.value);
            setSlashHighlight(0);
            setHashHighlight(0);
          }}
          onKeyDown={(e) => {
            // IME composition Enter (CJK input) must not send.
            if (e.nativeEvent.isComposing) return;
            if (e.key === "Escape" && menuOpen) {
              if (hashOpen) onInputChange(stripHashQuery(input));
              else if (input.startsWith("/")) onInputChange("");
              setSlashHighlight(0);
              setHashHighlight(0);
              return;
            }
            if ((e.key === "ArrowDown" || e.key === "ArrowUp") && menuOpen) {
              e.preventDefault();
              const dir = e.key === "ArrowDown" ? 1 : -1;
              if (hashOpen) {
                setHashHighlight((h) => (hashCandidates.length === 0 ? 0 : (h + dir + hashCandidates.length) % hashCandidates.length));
              } else {
                setSlashHighlight((h) => (h + dir + slashMatches.length) % slashMatches.length);
              }
              return;
            }
            if (e.key === "Enter" && !e.shiftKey) {
              // Textarea would insert a newline: suppress it, this key sends.
              e.preventDefault();
              if (hashOpen) {
                const picked = hashCandidates[hashHighlight] ?? hashCandidates[0];
                if (picked) {
                  pickRef(picked);
                  return;
                }
                // No candidates: fall through and send the literal text.
              } else if (slashParsed !== null && slashMatches.length > 0) {
                const exact = resolveSlashCommand(slashParsed.name);
                const picked = exact ?? slashMatches[slashHighlight];
                if (picked) runSlash(picked);
                return;
              }
              onSend();
            }
          }}
          onBlur={() => {
            setSlashHighlight(0);
            setHashHighlight(0);
          }}
          placeholder={
            loading
              ? t("composer.placeholderQueued")
              : compacting
                ? t("composer.compacting")
                : t("composer.placeholder")
          }
        />
        {/* Bottom toolbar: one compact row huddled right (reference:
            adjacent ghost controls + send, never spread full width). */}
        <div className="flex items-center justify-end gap-1 px-1 pb-1 pt-1.5">
          <div className="min-w-0 shrink-0 overflow-hidden">
            <ContextGauge
              used={used}
              window={win}
              usage={usage}
              estimatedPrompt={estimated}
              breakdown={breakdown}
            />
          </div>
          {/* Selectors stay enabled while streaming: the in-flight turn already
              snapshotted its model/effort, so switching only affects the next send. */}
          <div className="min-w-0 shrink-0">
            <GroupedModelSelect
              models={chatModels}
              value={selectedModelId}
              onChange={onModelChange}
              ariaLabel={t("composer.selectModel")}
              defaultProfile={defaultChatProfile}
            />
          </div>
          <div className="shrink-0 [&_button]:h-7 [&_button]:border-0 [&_button]:bg-transparent [&_button]:px-1.5 [&_button]:shadow-none [&_button]:min-w-[76px]">
            <EffortSelect
              model={selectedModel}
              value={effort}
              onChange={onEffortChange}
            />
          </div>
          <button
            type="button"
            onClick={loading ? onStop : onSend}
            disabled={compacting && !loading}
            className="btn-primary h-8 w-8 shrink-0 !rounded-full !p-0 disabled:opacity-50"
            aria-label={loading ? t("composer.stop") : compacting ? t("composer.compacting") : t("composer.send")}
          >
            {loading ? <Square size={13} fill="currentColor" /> : <Send size={14} />}
          </button>
        </div>
      </div>
    </div>
  );
}
