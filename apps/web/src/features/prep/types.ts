/**
 * @file types.ts
 * @description Prep chat view-model: message shape, stream options, and
 * stream-event handlers owned by the prep feature.
 */

import type { PrepSearchGroup, PrepToolStep } from "@/lib/api/contract";
import type { AskUserDialog, PrepCompactionEvent, PrepUsageStats } from "@/types";

/** One entry of the merged thinking/tool timeline, in arrival order. */
export type PrepTraceItem =
  | { kind: "thinking"; text: string }
  | { kind: "tool"; name: string; query: string; args?: Record<string, string>; result?: string }
  | { kind: "compaction"; before: number; after: number; summarized: boolean };

/** Parsed compaction summary card data (from a persisted summary block). */
export interface PrepCompactionCard {
  summary: string;
  version: number;
  forkPoint: number | null;
  backupSessionId: number | null;
  before: number | null;
  after: number | null;
}

export interface PrepChatMessage {
  id: string;
  role: "user" | "assistant" | "compaction";
  content: string;
  streaming?: boolean;
  searchGroups?: PrepSearchGroup[];
  steps?: PrepToolStep[];
  /** Non-streaming reasoning text captured from a tool-round think block. */
  thinking?: string;
  statusText?: string;
  /** Merged thinking/tool timeline in true arrival order. */
  trace?: PrepTraceItem[];
  /** True when the turn was stopped before completion (persists from backend). */
  stopped?: boolean;
  /** Index in the backend message list; absent for local-only messages. */
  backendIndex?: number;
  /** Compaction card payload (role "compaction" only). */
  compaction?: PrepCompactionCard;
  /**
   * Local-only message: never sent to (or stored by) the backend, so it never
   * enters model context. Welcome banners and failed-turn error text set this;
   * context estimation skips such messages.
   */
  localOnly?: boolean;
}

/** Stream options snapshotted per send: queued turns reuse the snapshot taken at enqueue time. */
export interface PrepStreamOptions {
  modelProfileId?: number | null;
  reasoningEffort?: string | null;
}

/** Stream-event callbacks owned by the prep send pipeline. */
export interface PrepStreamHandlers {
  onToken: (text: string) => void;
  onThinking: (text: string) => void;
  onSearchResults: (groups: PrepSearchGroup[]) => void;
  onStatus: (text: string) => void;
  onToolStep: (step: PrepToolStep) => void;
  onAskUser: (dialog: AskUserDialog) => void;
  onUsage: (usage: PrepUsageStats) => void;
  onCompaction?: (event: PrepCompactionEvent) => void;
}
