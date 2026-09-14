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

import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { TriangleAlert } from "lucide-react";
import { useT } from "@/i18n";
import { Spinner } from "@/components/Spinner";

/** Destructive-action dialog that focuses cancel by default and treats Escape as cancel. */
export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  cancelLabel,
  busy = false,
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
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const t = useT("common");
  // Explicit labels override the localized defaults.
  const okLabel = confirmLabel ?? t("confirm.confirm");
  const dismissLabel = cancelLabel ?? t("confirm.cancel");
  const cancelButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    // preventScroll: the dialog is a fixed overlay already in view; a plain
    // focus() would yank a scrolled page toward the overlay's document slot.
    cancelButtonRef.current?.focus({ preventScroll: true });
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
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

        <div className="mt-4 flex gap-2">
          <button
            ref={cancelButtonRef}
            type="button"
            className="btn-primary flex-1 !h-9"
            disabled={busy}
            onClick={onCancel}
          >
            {dismissLabel}
          </button>
          <button
            type="button"
            className="flex-1 rounded-md border border-[var(--danger)]/30 bg-surface-alt !h-9 text-[13px] font-medium text-[var(--danger-ink)] transition-colors hover:bg-[var(--danger-soft)] disabled:cursor-not-allowed disabled:opacity-45"
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? <Spinner className="mx-auto h-3.5 w-3.5" /> : okLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
