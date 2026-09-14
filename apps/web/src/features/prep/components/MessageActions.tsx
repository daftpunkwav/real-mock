"use client";

/**
 * @file MessageActions.tsx
 * @description Per-message action bars: assistant (copy/export/fork/regenerate/rate),
 * user (copy/fork/retract). Includes clipboard and markdown-download helpers.
 */

import { useState } from "react";
import {
  Check,
  Copy,
  Download,
  GitFork,
  RefreshCw,
  Star,
  Undo2,
} from "lucide-react";
import { toast } from "@/components/Toast";
import { useT } from "@/i18n";
import { copyTextToClipboard } from "@/lib/clipboard";
import { downloadTextFile } from "@/lib/download";
import { cn } from "@/lib/utils";

/** Copy text (shared helper; re-exported for backward compatibility). */
export const copyText = copyTextToClipboard;

/** Download text as a UTF-8 markdown file (shared helper). */
export function downloadMarkdown(filename: string, text: string): void {
  downloadTextFile(filename, text);
}

function ActionButton({
  title,
  onClick,
  disabled,
  children,
}: {
  title: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      disabled={disabled}
      onClick={onClick}
      className="flex h-6 w-6 items-center justify-center rounded text-ink-subtle transition-colors hover:bg-surface-muted hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  );
}

export function AssistantMessageActions({
  content,
  onExport,
  onFork,
  onRegenerate,
  onRate,
}: {
  content: string;
  onExport: () => void;
  onFork?: () => void;
  /** Absent for archived (folded) messages: regeneration needs live context. */
  onRegenerate?: () => void;
  /** Absent for archived messages. */
  onRate?: () => void;
}) {
  const t = useT("prep");
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!content) return;
    const ok = await copyText(content);
    if (ok) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } else {
      toast.error(t("actions.copyFailed"));
    }
  };

  return (
    <div className={cn("mt-1.5 flex items-center gap-0.5", !content && "hidden")}>
      <ActionButton title={t("actions.copy")} onClick={() => void handleCopy()}>
        {copied ? <Check size={13} className="text-[var(--success)]" /> : <Copy size={13} />}
      </ActionButton>
      <ActionButton title={t("actions.export")} onClick={onExport}>
        <Download size={13} />
      </ActionButton>
      {onFork ? (
        <ActionButton title={t("actions.fork")} onClick={onFork}>
          <GitFork size={13} />
        </ActionButton>
      ) : null}
      {onRegenerate ? (
        <ActionButton title={t("actions.regenerate")} onClick={onRegenerate}>
          <RefreshCw size={13} />
        </ActionButton>
      ) : null}
      {onRate ? (
        <ActionButton title={t("actions.rate")} onClick={onRate}>
          <Star size={13} />
        </ActionButton>
      ) : null}
    </div>
  );
}

export function UserMessageActions({
  content,
  onFork,
  onRetract,
}: {
  content: string;
  onFork?: () => void;
  /** Absent for archived messages: retraction needs live indices. */
  onRetract?: () => void;
}) {
  const t = useT("prep");
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!content) return;
    const ok = await copyText(content);
    if (ok) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } else {
      toast.error(t("actions.copyFailed"));
    }
  };

  return (
    <div className="mt-1.5 flex items-center justify-end gap-0.5">
      <ActionButton title={t("actions.copy")} onClick={() => void handleCopy()}>
        {copied ? <Check size={13} className="text-[var(--success)]" /> : <Copy size={13} />}
      </ActionButton>
      {onFork ? (
        <ActionButton title={t("actions.fork")} onClick={onFork}>
          <GitFork size={13} />
        </ActionButton>
      ) : null}
      {onRetract ? (
        <ActionButton title={t("actions.retract")} onClick={onRetract}>
          <Undo2 size={13} />
        </ActionButton>
      ) : null}
    </div>
  );
}
