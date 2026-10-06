"use client";

/**
 * @file ConfirmDialog.tsx
 * @description Shared destructive-action confirm dialog.
 *
 * Responsibilities:
 * - Focus the safe (cancel) action on open; Escape maps to cancel
 * - Optional busy state disables both buttons and blocks Escape (in-flight confirm)
 *
 * Profile and resume both use this component; do not fork copies into features.
 */

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { TriangleAlert } from "lucide-react";
import { useT } from "@/i18n";
import { Spinner } from "@/components/Spinner";
import { useDialogScrollLock } from "@/components/useDialogScrollLock";

/** Acknowledgement checkbox gate for extra-destructive confirmations. */
const AcknowledgementCheckbox = ({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) => (
  <label className="mt-4 flex cursor-pointer items-start gap-2 rounded-md border border-surface-border bg-surface-alt px-3 py-2.5">
    <input
      type="checkbox"
      className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-[var(--danger)]"
      checked={checked}
      onChange={(e) => {
        onChange(e.target.checked);
      }}
    />
    <span className="text-[12px] leading-relaxed text-ink-muted">{label}</span>
  </label>
);

interface DialogActionsProps {
  confirmLabel?: string;
  cancelLabel?: string;
  requireAcknowledgement: boolean;
  acknowledged: boolean;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Confirm stays locked while in flight and until the acknowledgement box is ticked. */
function isConfirmLocked(
  busy: boolean,
  requireAcknowledgement: boolean,
  acknowledged: boolean,
): boolean {
  return busy || (requireAcknowledgement && !acknowledged);
}

/** Cancel/confirm button row; owns labels, cancel-focus, and the locked logic. */
const DialogActions = ({
  confirmLabel,
  cancelLabel,
  requireAcknowledgement,
  acknowledged,
  busy,
  onConfirm,
  onCancel,
}: DialogActionsProps) => {
  const translator = useT("common");
  const cancelButtonRef = useRef<HTMLButtonElement>(null);
  // preventScroll: the dialog is a fixed overlay already in view; a plain
  // focus() would yank a scrolled page toward the overlay's document slot.
  useEffect(() => {
    cancelButtonRef.current?.focus({ preventScroll: true });
  }, []);
  // Explicit labels override the localized defaults.
  const locked = isConfirmLocked(busy, requireAcknowledgement, acknowledged);
  return (
    <div className="mt-4 flex gap-2">
      <button
        ref={cancelButtonRef}
        type="button"
        className="btn-primary flex-1 !h-9"
        disabled={busy}
        onClick={onCancel}
      >
        {cancelLabel ?? translator("confirm.cancel")}
      </button>
      <button
        type="button"
        className="btn-danger flex-1 !h-9"
        disabled={locked}
        onClick={onConfirm}
      >
        {busy ? (
          <Spinner className="mx-auto h-3.5 w-3.5" />
        ) : (
          (confirmLabel ?? translator("confirm.confirm"))
        )}
      </button>
    </div>
  );
};

/** Destructive-action dialog that focuses cancel by default and treats Escape as cancel. */
export const ConfirmDialog = ({
  open,
  title,
  message,
  confirmLabel,
  cancelLabel,
  busy = false,
  requireAcknowledgement = false,
  acknowledgementLabel = "",
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** When true, both actions are disabled and Escape is ignored. */
  busy?: boolean;
  /** Require ticking a checkbox before confirm unlocks (extra guard against mis-clicks). */
  requireAcknowledgement?: boolean;
  /** Label for the acknowledgement checkbox (requires requireAcknowledgement). */
  acknowledgementLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) => {
  useDialogScrollLock(open);
  const [acknowledged, setAcknowledged] = useState(false);
  // Reset the checkbox whenever the dialog reopens so a previous session's
  // tick cannot silently unlock a fresh confirmation. Render-phase adjust:
  // resetting in an effect would fire a cascading re-render instead.
  const [prevOpen, setPrevOpen] = useState(open);
  if (open !== prevOpen) {
    setPrevOpen(open);
    if (open) setAcknowledged(false);
  }

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [open, busy, onCancel]);

  if (!open) return null;

  // Portal out of the page tree: entrance animations above retain an identity
  // transform, which would otherwise contain this fixed overlay to a content
  // box instead of the viewport (partial dimming).
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 anim-fade-in"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div className="surface-card w-full max-w-md !p-5 anim-rise">
        <div className="flex items-start gap-3">
          <span className="icon-badge icon-badge-danger shrink-0">
            <TriangleAlert size={16} strokeWidth={1.75} />
          </span>
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--danger)]">
              {title}
            </p>
            <p className="mt-1 text-[14px] font-medium leading-relaxed text-ink">{message}</p>
          </div>
        </div>

        {requireAcknowledgement ? (
          <AcknowledgementCheckbox
            label={acknowledgementLabel}
            checked={acknowledged}
            onChange={setAcknowledged}
          />
        ) : null}

        <DialogActions
          confirmLabel={confirmLabel}
          cancelLabel={cancelLabel}
          requireAcknowledgement={requireAcknowledgement}
          acknowledged={acknowledged}
          busy={busy}
          onConfirm={onConfirm}
          onCancel={onCancel}
        />
      </div>
    </div>,
    document.body,
  );
};
