"use client";

import { useT } from "@/i18n";
import { Send } from "lucide-react";
import { ChatBubble } from "./ChatBubble";
import type { InterviewRoomModel } from "../hooks/room";

/** Chat column: message flow + streaming + empty state + text/recording sending line. */
export function InterviewRoomChat({ room }: { room: InterviewRoomModel }) {
  const {
    messages,
    streamingText,
    chatEndRef,
    sessionStatus,
    canInput,
    inputText,
    setInputText,
    canSend,
    handleSend,
    isRecording,
  } = room;
  const t = useT("interview");

  return (
    <div className="rounded-lg border border-surface-border bg-surface-card flex flex-col min-h-0">
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {messages.length === 0 && !streamingText && (
          <p className="text-xs text-ink-subtle text-center py-6">
            {sessionStatus === "active" ? t("chat.empty.restored") : t("chat.empty.starting")}
          </p>
        )}
        {messages.map((m, i) => (
          <ChatBubble key={i} role={m.role} content={m.content} />
        ))}
        {streamingText && <ChatBubble role="assistant" content={streamingText} streaming />}
        <div ref={chatEndRef} />
      </div>

      <div className="border-t border-surface-border p-2 flex gap-2 shrink-0">
        <input
          className="flex-1 rounded-md border border-surface-border bg-surface-card px-3 py-2.5 text-[13px] text-ink placeholder:text-ink-subtle focus:border-[var(--primary)] focus:shadow-focus focus:outline-none disabled:opacity-40"
          placeholder={canInput ? t("chat.input.placeholder") : t("chat.input.waiting")}
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
          disabled={!canInput}
        />
        <button
          type="button"
          onClick={handleSend}
          disabled={!canSend}
          className="btn-primary !h-10 !w-10 shrink-0 !px-0 disabled:!bg-surface-muted disabled:!text-ink-subtle"
          title={inputText.trim() ? t("chat.send.text") : isRecording ? t("chat.send.voice") : t("chat.send.hint")}
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  );
}
