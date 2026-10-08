"use client";

/**
 * @file DangerActionCard.tsx
 * @description Shared destructive settings card: icon+title header, description,
 * danger action button, and the confirm dialog guarding the action.
 */

import { useState, type ReactNode } from "react";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { useT } from "@/i18n";

/**
 * One destructive settings row: renders the card scaffold shared by the
 * settings panels and owns the confirm-dialog/busy state machine. The caller
 * toasts outcomes; a thrown error keeps the dialog open with busy cleared.
 */
export const DangerActionCard = ({
  icon,
  title,
  description,
  actionLabel,
  confirmTitle,
  confirmBody,
  disabled = false,
  actionIcon = null,
  acknowledgementLabel,
  onConfirm,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  actionLabel: string;
  confirmTitle: string;
  confirmBody: string;
  disabled?: boolean;
  actionIcon?: ReactNode;
  /** When set, confirm stays locked until the user ticks this acknowledgement. */
  acknowledgementLabel?: string;
  /** Runs the destructive action; must throw on failure so the dialog stays open. */
  onConfirm: () => Promise<void>;
}) => {
  const tc = useT("common");
  const [confirming, setConfirming] = useState(false);
  const [running, setRunning] = useState(false);

  const handleConfirm = async () => {
    setRunning(true);
    try {
      await onConfirm();
      // Clear busy before closing: the dialog restores focus to the action
      // trigger on close, and a disabled trigger would swallow it.
      setRunning(false);
      setConfirming(false);
    } catch {
      // Failure keeps the dialog open; the caller already toasted the error.
      setRunning(false);
    }
  };

  return (
    <div className="surface-card p-4">
      <div className="mb-1 flex items-center gap-2">
        {icon}
        <h2 className="text-[14px] font-semibold">{title}</h2>
      </div>
      <p className="text-[13px] leading-relaxed text-ink-muted">{description}</p>
      <button
        type="button"
        className="btn-danger mt-3 text-[13px]"
        disabled={disabled || running}
        onClick={() => setConfirming(true)}
      >
        {actionIcon}
        {actionLabel}
      </button>
      <ConfirmDialog
        open={confirming}
        title={confirmTitle}
        message={confirmBody}
        confirmLabel={actionLabel}
        cancelLabel={tc("confirm.cancel")}
        busy={running}
        requireAcknowledgement={acknowledgementLabel != null}
        acknowledgementLabel={acknowledgementLabel ?? ""}
        onConfirm={() => void handleConfirm()}
        onCancel={() => setConfirming(false)}
      />
    </div>
  );
};
