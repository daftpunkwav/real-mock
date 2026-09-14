/** WebSocket turn-protocol events (Server → Client / Client → Server).
 *
 * Protocol SSOT: protocol/interview_ws.schema.json; REST contract: `@/lib/api/contract`.
 */

import type { SSEErrorEvent } from "./interview_prep";

/** Multimodal input: candidate vision-frame analysis (with user_text / vision_update uplink). */
export interface FaceAnalysis {
  dominant_emotion?: string;
  emotion_scores?: Record<string, string>;
  eye_contact?: boolean;
  smile?: boolean;
  confidence?: number;
  timestamp_ms?: number;
  [extra: string]: unknown;
}

export type TurnState = "IDLE" | "AI_SPEAKING" | "USER_SPEAKING" | "PROCESSING";

export type ServerEvent =
  | { type: "turn_state"; state: TurnState }
  | { type: "assistant_token"; token: string; phase?: string }
  | {
      type: "assistant_done";
      content: string;
      phase: string;
      emotion?: string;
      is_complete: boolean;
      audio_b64?: string;
      playback_generation?: number;
      /** Expected candidate answer seconds (turn protocol; 0/missing = not provided) */
      wait_seconds?: number;
      /** Answer grounding for this turn: resume | github | company_kb | none */
      sources?: string[];
      /** Agent verdict on the wrap-up turn: passed | failed | null */
      result?: string | null;
      /** Agent-authored current step title (plan mode; null = static phase id). */
      phase_title?: string | null;
    }
  | { type: "stt_partial"; text: string }
  | { type: "stt_final"; text: string }
  | {
      type: "tts_audio";
      data: string;
      mime?: string;
      sentence?: string;
      playback_generation?: number;
    }
  | { type: "tts_failed"; message: string }
  | { type: "tts_interrupted"; reason?: string; candidate_interrupts?: number; playback_generation?: number }
  | { type: "silence_nudge"; content: string; seq?: number; ai_interrupts?: number }
  | { type: "reference_hint_loading"; question: string }
  | { type: "reference_hint"; content: string; question: string }
  | { type: "phase_changed"; phase: string; phase_title?: string | null }
  | {
      type: "interview_complete";
      session_id?: number;
      overall_score?: number | null;
      /** Agent verdict: passed | failed | null */
      result?: string | null;
    }
  | { type: "server_ping"; t: number }
  | {
      type: "info";
      message: string;
      fallback?: boolean;
      provider?: string;
      requested_provider?: string | null;
    }
  | SSEErrorEvent;

export type ClientEvent =
  | {
      type: "user_text";
      text: string;
      face_analysis?: FaceAnalysis;
      image_base64?: string;
    }
  | {
      type: "user_turn_end";
      pcm: string;
      sample_rate: number;
      text?: string;
      face_analysis?: FaceAnalysis;
      image_base64?: string;
    }
  | { type: "stt_text"; text: string }
  | { type: "silence_timeout" }
  | { type: "barge_in" }
  | { type: "request_hint"; question: string }
  | { type: "request_finish" }
  | { type: "vision_update"; face_analysis: FaceAnalysis }
  | { type: "tts_playback_done"; generation?: number }
  | { type: "pong"; t: number };
