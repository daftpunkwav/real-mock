"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ClientEvent, ServerEvent, TurnState } from "@/types";
import { resolveBackendWsUrl } from "@/lib/api/apiUrl";

type ServerHandler<K extends ServerEvent["type"]> = (
  msg: Extract<ServerEvent, { type: K }>,
) => void;

export type WSHandlers = {
  [K in ServerEvent["type"]]?: ServerHandler<K>;
};

type WSConnectionState = "connecting" | "open" | "reconnecting" | "failed";

/**
 * Interview WebSocket with typed handlers and generation-guarded reconnect.
 */
export function useInterviewWS(
  sessionId: number,
  handlers?: WSHandlers,
  options?: { maxRetries?: number },
) {
  const wsRef = useRef<WebSocket | null>(null);
  const handlersRef = useRef<Record<string, (msg: ServerEvent) => void>>({});
  const retryTimerRef = useRef<number | null>(null);
  const retryCountRef = useRef(0);
  /** Generation guard against stale effects and sockets. */
  const generationRef = useRef(0);
  const [connected, setConnected] = useState(false);
  /** Tracks whether the socket has connected at least once. */
  const [everConnected, setEverConnected] = useState(false);
  const [turnState, setTurnState] = useState<TurnState>("IDLE");
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const [connectionState, setConnectionState] = useState<WSConnectionState>("connecting");
  const [reconnectKey, setReconnectKey] = useState(0);
  const maxRetries = options?.maxRetries ?? 5;

  useEffect(() => {
    if (handlers) {
      const next: Record<string, (msg: ServerEvent) => void> = {};
      for (const [type, handler] of Object.entries(handlers)) {
        if (handler) next[type] = handler as (msg: ServerEvent) => void;
      }
      handlersRef.current = next;
    }
  }, [handlers]);

  const on = useCallback(<K extends ServerEvent["type"]>(type: K, handler: ServerHandler<K>) => {
    handlersRef.current[type] = handler as (msg: ServerEvent) => void;
  }, []);

  const send = useCallback((payload: ClientEvent) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
      return true;
    }
    return false;
  }, []);

  const clearRetryTimer = useCallback(() => {
    if (retryTimerRef.current !== null) {
      window.clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  }, []);

  const cancel = useCallback(() => {
    generationRef.current += 1;
    clearRetryTimer();
    const ws = wsRef.current;
    wsRef.current = null;
    if (ws) {
      try {
        ws.close(1000, "client_cancel");
      } catch {
        /* noop */
      }
    }
    setConnected(false);
    setConnectionState("connecting");
  }, [clearRetryTimer]);

  const retryNow = useCallback(() => {
    retryCountRef.current = 0;
    setReconnectAttempt(0);
    setConnectionState("connecting");
    setReconnectKey((k) => k + 1);
  }, []);

  useEffect(() => {
    // Own this effect generation; stale callbacks bail out.
    const generation = ++generationRef.current;
    retryCountRef.current = 0;
    setEverConnected(false);
    setConnected(false);
    setTurnState("IDLE");
    setReconnectAttempt(0);
    setConnectionState("connecting");
    clearRetryTimer();

    const isCurrent = () => generationRef.current === generation;

    if (!Number.isFinite(sessionId) || sessionId <= 0) {
      return () => {
        generationRef.current += 1;
        clearRetryTimer();
      };
    }

    const connect = () => {
      if (!isCurrent()) return;

      // Close the previous socket before opening a new one.
      const prev = wsRef.current;
      if (prev) {
        try {
          prev.onclose = null;
          prev.onerror = null;
          prev.onmessage = null;
          prev.close(1000, "replace");
        } catch {
          /* noop */
        }
        if (wsRef.current === prev) wsRef.current = null;
      }

      // Resolve through the shared loopback alignment so the WS host matches
      // the REST host the session cookie was issued for.
      const url = resolveBackendWsUrl(`/api/v1/ws/interview/${sessionId}`);
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isCurrent() || wsRef.current !== ws) {
          try {
            ws.close(1000, "stale");
          } catch {
            /* noop */
          }
          return;
        }
        retryCountRef.current = 0;
        setReconnectAttempt(0);
        setConnected(true);
        setEverConnected(true);
        setConnectionState("open");
      };

      ws.onclose = (ev) => {
        // Ignore close events from stale sockets.
        if (!isCurrent() || wsRef.current !== ws) return;
        wsRef.current = null;
        setConnected(false);

        // Skip reconnect for intentional client-side closes.
        if (ev.code === 1000 && (ev.reason === "client_cancel" || ev.reason === "replace" || ev.reason === "stale")) {
          return;
        }

        retryCountRef.current += 1;
        if (retryCountRef.current > maxRetries) {
          // Mark failed after max retries; keep probing every 20s so a
          // restarted backend is picked up without manual action.
          setConnectionState("failed");
          clearRetryTimer();
          retryTimerRef.current = window.setTimeout(() => {
            if (isCurrent()) connect();
          }, 20_000);
          return;
        }
        setReconnectAttempt(retryCountRef.current);
        setConnectionState("reconnecting");
        const delay = Math.min(1000 * 2 ** (retryCountRef.current - 1), 8000);
        clearRetryTimer();
        retryTimerRef.current = window.setTimeout(() => {
          if (isCurrent()) connect();
        }, delay);
      };

      ws.onerror = () => {
        // Delegate to onclose for reconnect handling.
        try {
          ws.close();
        } catch {
          /* noop */
        }
      };

      ws.onmessage = (ev) => {
        if (!isCurrent() || wsRef.current !== ws) return;
        try {
          const msg = JSON.parse(ev.data) as ServerEvent;
          if (msg.type === "turn_state") {
            setTurnState(msg.state);
          }
          if (msg.type === "server_ping") {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: "pong", t: msg.t }));
            }
            return;
          }
          const handler = handlersRef.current[msg.type];
          if (handler) handler(msg);
        } catch {
          /* ignore malformed frame */
        }
      };
    };

    connect();

    return () => {
      // Cleanup guards stale callbacks and closes the socket.
      generationRef.current += 1;
      clearRetryTimer();
      const ws = wsRef.current;
      wsRef.current = null;
      if (ws) {
        try {
          ws.onclose = null;
          ws.onerror = null;
          ws.onmessage = null;
          ws.close(1000, "client_cancel");
        } catch {
          /* noop */
        }
      }
    };
  }, [sessionId, maxRetries, reconnectKey, clearRetryTimer]);

  return {
    connected,
    everConnected,
    turnState,
    reconnectAttempt,
    connectionState,
    send,
    on,
    cancel,
    retryNow,
  };
}
