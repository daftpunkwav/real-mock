"use client";

/**
 * @file usePrepScroll.ts
 * @description Prep chat auto-follow scroll state.
 */

import { useCallback, useEffect, useRef, useState } from "react";

/** Near-bottom distance that keeps auto-follow enabled. */
const FOLLOW_THRESHOLD_PX = 96;

export function usePrepScroll(messagesLength: number) {
  const [showJump, setShowJump] = useState(false);
  const chatScrollRef = useRef<HTMLDivElement>(null);
  /** Content node observed to keep the view pinned. */
  const contentRef = useRef<HTMLDivElement>(null);
  const followRef = useRef(true);

  const handleScroll = useCallback(() => {
    const el = chatScrollRef.current;
    if (!el) return;
    const atBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < FOLLOW_THRESHOLD_PX;
    followRef.current = atBottom;
    setShowJump(!atBottom);
  }, []);

  useEffect(() => {
    const content = contentRef.current;
    if (!content || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (!followRef.current) return;
      const el = chatScrollRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, [messagesLength]);

  const jumpToBottom = useCallback(() => {
    followRef.current = true;
    setShowJump(false);
    const el = chatScrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, []);

  const stickToBottom = useCallback(() => {
    followRef.current = true;
    setShowJump(false);
  }, []);

  return {
    showJump,
    chatScrollRef,
    contentRef,
    followRef,
    handleScroll,
    jumpToBottom,
    stickToBottom,
  };
}
