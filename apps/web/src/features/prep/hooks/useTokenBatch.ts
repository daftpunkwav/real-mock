"use client";

/** Batch streaming tokens into one rAF flush. */

import { useCallback, useEffect, useRef } from "react";
import type { PrepChatMessage } from "../types";

export function useTokenBatch(
  setMessages: React.Dispatch<React.SetStateAction<PrepChatMessage[]>>,
) {
  const pendingTokenRef = useRef<{ id: string; text: string } | null>(null);
  const rafRef = useRef(0);

  const flushPendingToken = useCallback(() => {
    rafRef.current = 0;
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
    },
    [flushPendingToken],
  );

  useEffect(
    () => () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    },
    [],
  );

  return { flushPendingToken, queueToken };
}
