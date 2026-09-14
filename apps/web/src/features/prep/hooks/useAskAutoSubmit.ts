"use client";

/**
 * @file useAskAutoSubmit.ts
 * @description Deadline auto-submit for single-question ask dialogs: fires the
 * recommended choice once when the countdown reaches zero. Deadline-based (not
 * duration-based) so background tabs still expire on time. Skipped while the
 * user composes custom text and never for multi-question forms.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { readAskTimeoutSec } from "@/lib/askTimeout";

export function useAskAutoSubmit(
  autoChoice: string | null,
  isComposing: boolean,
  disabled: boolean,
  onFire: (choice: string) => void,
): { remainingMs: number | null; formatRemaining: (ms: number) => string } {
  const timeoutSec = useMemo(() => readAskTimeoutSec(), []);
  const deadline = useMemo(
    () => (timeoutSec > 0 && autoChoice && !disabled ? Date.now() + timeoutSec * 1000 : null),
    [timeoutSec, autoChoice, disabled],
  );
  const [now, setNow] = useState(() => Date.now());
  const firedRef = useRef(false);
  // A new dialog re-arms the one-shot guard (the modal stays mounted).
  useEffect(() => {
    firedRef.current = false;
    setNow(Date.now());
  }, [autoChoice]);
  useEffect(() => {
    if (deadline === null) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [deadline]);
  const remainingMs = deadline === null ? null : Math.max(0, deadline - now);
  useEffect(() => {
    if (remainingMs === 0 && autoChoice && !firedRef.current && !isComposing && !disabled) {
      firedRef.current = true;
      onFire(autoChoice);
    }
  }, [remainingMs, autoChoice, isComposing, disabled, onFire]);

  const formatRemaining = (ms: number): string => {
    const total = Math.ceil(ms / 1000);
    return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
  };
  return { remainingMs, formatRemaining };
}
