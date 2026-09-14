/**
 * Records / ledger domain types (history list + session ledger replay).
 * Hand-written; OpenAPI contract may lag the records domain.
 */

export type ToolPreview = {
  name?: string;
  args_preview?: unknown;
  result_preview?: unknown;
  ok?: boolean;
  chars?: number;
};

export type LedgerAssistant = {
  text?: string;
  visible?: boolean;
};

export type LedgerUser = {
  text?: string;
  source?: string;
};

export type LedgerTurn = {
  turn_id?: string;
  phase?: string;
  assistant?: LedgerAssistant;
  tools?: ToolPreview[];
  user?: LedgerUser;
  flags?: Record<string, unknown>;
};

export type LedgerDocument = {
  schema?: string;
  session_id?: number;
  frozen?: boolean;
  turns?: LedgerTurn[];
};

/** GET /v1/records/sessions item shape. */
export type SessionHistoryItem = {
  id: number;
  role: string;
  level: string;
  company: string;
  workflow_type: string;
  personality: string;
  strictness: number;
  interview_style: string;
  avatar_id?: string;
  scene_id?: string;
  status: string;
  current_phase: string;
  overall_score?: number | null;
  /** Multi-round lineage (null = standalone session). */
  process_id?: number | null;
  round_no?: number | null;
  /** Agent-announced verdict: passed | failed | null (unjudged). */
  result?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  created_at?: string | null;
  ledger_frozen?: boolean;
};
