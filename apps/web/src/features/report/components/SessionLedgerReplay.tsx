/**
 * Session ledger replay timeline for the report page.
 * Renders assistant / tools / user turns from a frozen (or prefix) ledger.
 */

"use client";

import { useState } from "react";
import { useT } from "@/i18n";
import type { LedgerDocument, LedgerTurn, ToolPreview } from "@/types/domains/records";

function formatPreview(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function ToolBlock({ tool }: { tool: ToolPreview }) {
  const [open, setOpen] = useState(false);
  const t = useT("report");
  const name = tool.name || t("turns.toolNameFallback");
  const ok = tool.ok !== false;

  return (
    <div className="rounded border border-surface-border bg-surface-alt">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-[12px] text-ink"
      >
        <span className="min-w-0 truncate font-medium">
          {name}
          <span className={`ml-2 text-[10px] ${ok ? "text-[var(--success-ink)]" : "text-[var(--danger-ink)]"}`}>
            {ok ? t("turns.toolOk") : t("turns.toolFail")}
          </span>
        </span>
        <span className="shrink-0 text-[10px] uppercase tracking-wide text-ink-subtle">
          {open ? t("turns.collapse") : t("turns.expand")}
        </span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-surface-border px-3 py-2 text-[11px] leading-relaxed text-ink-muted">
          {tool.args_preview != null && (
            <div>
              <p className="mb-0.5 text-[10px] uppercase tracking-[0.08em] text-ink-subtle">{t("turns.toolArgs")}</p>
              <pre className="whitespace-pre-wrap break-words font-mono">{formatPreview(tool.args_preview)}</pre>
            </div>
          )}
          {tool.result_preview != null && (
            <div>
              <p className="mb-0.5 text-[10px] uppercase tracking-[0.08em] text-ink-subtle">{t("turns.toolResult")}</p>
              <pre className="whitespace-pre-wrap break-words font-mono">{formatPreview(tool.result_preview)}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function TurnBlock({ turn, index }: { turn: LedgerTurn; index: number }) {
  const t = useT("report");
  const assistantText = turn.assistant?.text?.trim() || "";
  const userText = turn.user?.text?.trim() || "";
  const tools = turn.tools ?? [];
  const label = turn.turn_id || `turn-${index + 1}`;

  return (
    <li className="relative border-l border-surface-border pl-4">
      <span className="absolute -left-[5px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-[var(--primary)] bg-surface-card" />
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-semibold text-ink">{label}</span>
        {turn.phase && <span className="chip chip-gray">{turn.phase}</span>}
      </div>

      {assistantText && (
        <div className="mb-2 rounded-md border border-surface-border bg-surface-card p-3">
          <p className="mb-1 text-[10px] uppercase tracking-[0.08em] text-ink-subtle">{t("turns.interviewer")}</p>
          <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-ink">{assistantText}</p>
        </div>
      )}

      {tools.length > 0 && (
        <div className="mb-2 space-y-1.5">
          <p className="text-[10px] uppercase tracking-[0.08em] text-ink-subtle">{t("turns.tools")}</p>
          {tools.map((tool, i) => (
            <ToolBlock key={`${label}-tool-${i}`} tool={tool} />
          ))}
        </div>
      )}

      {userText && (
        <div className="rounded-md border border-surface-border bg-[var(--info-soft)] p-3">
          <p className="mb-1 text-[10px] uppercase tracking-[0.08em] text-ink-subtle">{t("turns.candidate")}</p>
          <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-ink">{userText}</p>
        </div>
      )}
    </li>
  );
}

/** Timeline of ledger turns for session replay on the report page. */
export function SessionLedgerReplay({ ledger }: { ledger: LedgerDocument }) {
  const t = useT("report");
  const turns = ledger.turns ?? [];
  if (turns.length === 0) return null;

  return (
    <section className="mb-5 rounded-md border border-surface-border bg-surface-card p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[13px] font-semibold tracking-tight text-ink">{t("turns.replayTitle")}</h2>
        <div className="flex items-center gap-2">
          {ledger.frozen && <span className="chip chip-green">{t("turns.ledgerFrozen")}</span>}
          <span className="chip chip-gray">{t("turns.count", { count: turns.length })}</span>
        </div>
      </div>
      <ol className="space-y-4">
        {turns.map((turn, i) => (
          <TurnBlock key={turn.turn_id || `turn-${i}`} turn={turn} index={i} />
        ))}
      </ol>
    </section>
  );
}
