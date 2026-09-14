"use client";

/**
 * @file useTokenBatch.ts
 * @description Batch streaming tokens into one rAF flush, with a setTimeout
 * fallback: background tabs pause rAF, so a pending flush also arms a timer
 * to avoid content lagging when the tab regains focus mid-stream.
 */

import { useCallback, useEffect, useRef } from "react";
import type { PrepChatMessage } from "../types";

/** Fallback flush delay when rAF is paused (background tab). */
const BACKGROUND_FLUSH_MS = 500;

export function useTokenBatch(
  setMessages: React.Dispatch<React.SetStateAction<PrepChatMessage[]>>,
) {
  const pendingTokenRef = useRef<{ id: string; text: string } | null>(null);
  const rafRef = useRef(0);
  const timerRef = useRef(0);

  const flushPendingToken = useCallback(() => {
    rafRef.current = 0;
    if (timerRef.current) {
      window.clearTimeout(timerRef.current);
      timerRef.current = 0;
    }
    const p = pendingTokenRef.current;
    if (!p) return;
    pendingTokenRef.current = null;
    setMessages((m) =>
      m.map((msg) =>
        msg.id === p.id ? { ...msg, content: msg.content + p.text } : msg,
      ),
    );
  }, [setMessages]);

  const queueToken = useCallback(
    (id: string, text: string) => {
      const p = pendingTokenRef.current;
      if (p && p.id === id) {
        p.text += text;
      } else {
        if (p) flushPendingToken();
        pendingTokenRef.current = { id, text };
      }
      if (!rafRef.current) {
        rafRef.current = requestAnimationFrame(flushPendingToken);
      }
      // rAF never fires while the tab is hidden; the timer guarantees the
      // flush still lands (flushPendingToken clears it when rAF wins).
      if (!timerRef.current) {
        timerRef.current = window.setTimeout(flushPendingToken, BACKGROUND_FLUSH_MS);
      }
    },
    [flushPendingToken],
  );

  useEffect(
    () => () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      if (timerRef.current) window.clearTimeout(timerRef.current);
    },
    [],
  );

  return { flushPendingToken, queueToken };
}
