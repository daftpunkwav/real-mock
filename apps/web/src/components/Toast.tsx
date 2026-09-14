"use client";

/**
 * Toast system.
 *
 * Usage:
 * ```tsx
 * import { Toaster, toast } from "@/components/Toast";
 *
 * // Mount once near the top of layout.tsx
 * <Toaster />
 *
 * // Call from anywhere
 * toast.success("Resume uploaded");
 * toast.error("Upload failed: " + e.message);
 * ```
 *
 * Design notes:
 * - Module-level array + listener set broadcast state; ``Toaster`` subscribes via ``useState`` + ``useEffect``;
 * - Auto-dismiss after 4s by default; pass ``persist: true`` to keep it;
 * - Motion via framer-motion; icons via lucide-react.
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, XCircle, Info, AlertTriangle, X } from "lucide-react";
import { useT } from "@/i18n";

type ToastKind = "info" | "success" | "warning" | "error";

interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
  persist?: boolean;
  durationMs?: number;
}

type Listener = (items: ToastItem[]) => void;

const _items: ToastItem[] = [];
const _listeners = new Set<Listener>();
let _seq = 0;

function emit() {
  for (const l of _listeners) l(_items.slice());
}

function push(item: ToastItem) {
  _items.push(item);
  emit();
}

function remove(id: number) {
  const idx = _items.findIndex((t) => t.id === id);
  if (idx >= 0) {
    _items.splice(idx, 1);
    emit();
  }
}

function clearAll() {
  if (_items.length === 0) return;
  _items.splice(0, _items.length);
  emit();
}

export const toast = {
  show: (message: string, opts?: { kind?: ToastKind; persist?: boolean; durationMs?: number }) =>
    push({
      id: ++_seq,
      message,
      kind: opts?.kind ?? "info",
      persist: opts?.persist,
      durationMs: opts?.durationMs,
    }),
  success: (message: string, opts?: { persist?: boolean; durationMs?: number }) =>
    push({ id: ++_seq, message, kind: "success", persist: opts?.persist, durationMs: opts?.durationMs }),
  info: (message: string, opts?: { persist?: boolean; durationMs?: number }) =>
    push({ id: ++_seq, message, kind: "info", persist: opts?.persist, durationMs: opts?.durationMs }),
  warning: (message: string, opts?: { persist?: boolean; durationMs?: number }) =>
    push({ id: ++_seq, message, kind: "warning", persist: opts?.persist, durationMs: opts?.durationMs }),
  error: (message: string, opts?: { persist?: boolean; durationMs?: number }) =>
    push({ id: ++_seq, message, kind: "error", persist: opts?.persist, durationMs: opts?.durationMs }),
  dismiss: (id: number) => remove(id),
  clear: () => clearAll(),
};

const ICONS: Record<ToastKind, ReactNode> = {
  info: <Info className="text-[var(--primary)]" size={16} />,
  success: <CheckCircle2 className="text-[var(--success)]" size={16} />,
  warning: <AlertTriangle className="text-[var(--warning)]" size={16} />,
  error: <XCircle className="text-[var(--danger)]" size={16} />,
};

export function Toaster() {
  const [items, setItems] = useState<ToastItem[]>(_items);

  useEffect(() => {
    const l: Listener = (next) => setItems(next);
    _listeners.add(l);
    setItems(_items.slice());
    return () => {
      _listeners.delete(l);
    };
  }, []);

  return (
    <div
      aria-live="polite"
      aria-atomic="true"
      className="pointer-events-none fixed bottom-4 right-4 z-[1000] flex flex-col gap-2 max-w-sm w-[min(360px,calc(100vw-2rem))]"
    >
      <AnimatePresence mode="popLayout">
        {items.map((t) => (
          <ToastView key={t.id} item={t} />
        ))}
      </AnimatePresence>
    </div>
  );
}

function ToastView({ item }: { item: ToastItem }) {
  const t = useT("common");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const close = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    remove(item.id);
  }, [item.id]);

  useEffect(() => {
    if (item.persist) return;
    const ms = item.durationMs ?? 4000;
    timerRef.current = setTimeout(close, ms);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [item.persist, item.durationMs, close]);

  const kindAccent: Record<ToastKind, string> = {
    info: "border-l-[var(--primary)]",
    success: "border-l-[var(--success)]",
    warning: "border-l-[var(--warning)]",
    error: "border-l-[var(--danger)]",
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, x: 24, scale: 0.98 }}
      transition={{ duration: 0.18, ease: [0.2, 0, 0, 1] }}
      className={`pointer-events-auto flex items-start gap-2.5 rounded-md border border-surface-border bg-surface-card p-3 shadow-md border-l-[3px] ${kindAccent[item.kind]}`}
      role="status"
    >
      <div className="mt-0.5 shrink-0">{ICONS[item.kind]}</div>
      <p className="flex-1 text-[13px] leading-relaxed text-ink whitespace-pre-wrap">
        {item.message}
      </p>
      <button
        type="button"
        onClick={close}
        className="shrink-0"
        aria-label={t("action.close")}
      >
        <X size={14} className="text-ink-subtle hover:text-ink" />
      </button>
    </motion.div>
  );
}

