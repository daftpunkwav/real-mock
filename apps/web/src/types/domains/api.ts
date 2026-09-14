/** Processor config / voice catalog / model-profile type system. */

export type LLMProtocol = "openai_chat" | "anthropic_messages" | "openai_responses";

export interface StageModelCapabilities {
  supports_vision: boolean;
  supports_audio_input: boolean;
  supports_audio_output: boolean;
  supports_video_input: boolean;
}

export interface StageFallbackConfig {
  handler: string;
  mode: string;
}

export interface StageConfig {
  stage: string;
  provider: string;
  api_base: string;
  protocol: LLMProtocol;
  model: string;
  max_tokens: number;
  context_window: number;
  capabilities: StageModelCapabilities;
  fallback: StageFallbackConfig;
  extras: Record<string, unknown>;
  has_api_key: boolean;
  updated_at?: string;
  api_key?: string;
}

export interface StageConfigs {
  recognize: StageConfig;
  reason: StageConfig;
  speak: StageConfig;
  updated_at?: string;
}

export interface VoiceProviderOption {
  id: string;
  label: string;
  can_speech_recognize: boolean;
  can_interview_reason: boolean;
  can_speech_speak: boolean;
  recognize_via: "native_audio" | "transcribe_only" | "none";
  speak_via: "native_audio" | "tts_from_text" | "none";
  status: "ready" | "coming_soon";
  default_model?: string;
  default_api_base?: string;
  hint?: string;
}

export interface VoiceCatalog {
  reasoning: VoiceProviderOption[];
  recognize: VoiceProviderOption[];
  speak: VoiceProviderOption[];
}

/* ── Model profile system (capability declaration) ─────────────────────────── */

/** Neutral capability flags: a profile declares what it can do; reusable across task bindings */
export interface ModelCapabilities {
  chat: boolean;
  vision: boolean;
  audio_input: boolean;
  audio_output: boolean;
  reasoning: boolean;
}

/** Model profile (one model under a provider + capabilities + params) */
export interface ModelProfile {
  id: number;
  provider_id: number;
  provider_name: string;
  model: string;
  display_name: string;
  label: string;
  context_window: number;
  max_output: number;
  capabilities: ModelCapabilities;
  extras: Record<string, unknown>;
  enabled: boolean;
}

export interface ProviderWithModels {
  id: number;
  name: string;
  api_base: string;
  protocol: LLMProtocol;
  enabled: boolean;
  has_api_key: boolean;
  models: ModelProfile[];
}

export interface ModelProfileWrite {
  model: string;
  display_name?: string;
  context_window?: number;
  max_output?: number;
  capabilities?: Partial<ModelCapabilities>;
  extras?: Record<string, unknown>;
  enabled?: boolean;
}

export interface ProviderWrite {
  name?: string;
  api_base?: string;
  protocol?: LLMProtocol;
  api_key?: string;
  enabled?: boolean;
}

/** Task bindings: default handlers for chat / stt / tts */
export interface TaskBindingInfo {
  task: "chat" | "stt" | "tts";
  profile: ModelProfile | null;
  fallback: { handler: string; mode: string };
}

export type TaskBindings = Record<"chat" | "stt" | "tts", TaskBindingInfo>;

/** Reasoning effort (only profiles with capabilities.reasoning === true) */
export type ReasoningEffort = "low" | "medium" | "high" | "max";

/** Reference-answer depth: fast outline bullets (default) or tool-grounded full model answer */
export type ReferenceDetail = "outline" | "full";

export interface LLMTestResponse {
  success: boolean;
  message: string;
  model?: string | null;
  transcript?: string | null;
  audio_base64?: string | null;
  fallback?: string | null;
  latency_ms?: number | null;
}

/** Unified error response envelope */
export interface ApiErrorBody {
  code: string;
  message: string;
  hint?: string;
  retryable?: boolean;
  trace_id?: string;
}

export interface ApiErrorEnvelope {
  detail?: string;
  error?: ApiErrorBody;
}
