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

/* ── Recommended vendors (adapted) ─────────────────────────────────────────── */

/** One model-type entry under a recommended vendor (level 2 of the cascade). */
export interface RecommendedVendorCapability {
  /** Catalog provider id to use as the LlmProvider name (e.g. "minimax_speech") */
  provider_id: string;
  label: string;
  catalog_label: string;
  default_model: string;
  default_api_base: string;
  hint: string;
  /** True when a vendor descriptor JSON defines the request template */
  adapted: boolean;
  def?: {
    transport: string;
    models: string[];
    request: Record<string, unknown>;
    notes: string;
  };
}

/** Level 1 of the recommended-vendor cascade. */
export interface RecommendedVendor {
  id: string;
  label: string;
  docs: Record<string, string>;
  capabilities: Partial<Record<"reasoning" | "recognize" | "speak", RecommendedVendorCapability>>;
}

/* ── Model profile system (capability declaration) ─────────────────────────── */

/** Channel/model-entry kind: which tab a model lives under and whose connection it uses */
export type ModelKind = "chat" | "stt" | "tts";

/** Neutral capability flags: a profile declares what it can do; reusable across task bindings */
export interface ModelCapabilities {
  chat: boolean;
  vision: boolean;
  audio_input: boolean;
  audio_output: boolean;
  reasoning: boolean;
}

/** Connection settings for one model type (chat / stt / tts) under a provider */
export interface ProviderChannel {
  kind: ModelKind;
  /** Catalog vendor id (e.g. "minimax") selecting the deep request adapter; "" for custom */
  vendor: string;
  api_base: string;
  /** Full-URL mode: api_base is a complete endpoint used verbatim; protocol paths are skipped */
  full_url: boolean;
  protocol: LLMProtocol;
  has_api_key: boolean;
}

/** Model profile (one model under a provider + capabilities + params) */
export interface ModelProfile {
  id: number;
  provider_id: number;
  provider_name: string;
  /** Which provider channel/tab this entry belongs to */
  kind: ModelKind;
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
  enabled: boolean;
  /** Optional reference info, purely informational */
  website_url: string;
  notes: string;
  /** Per-type connection settings; missing kinds can be created by saving their tab */
  channels: ProviderChannel[];
  models: ModelProfile[];
}

export interface ModelProfileWrite {
  model: string;
  kind?: ModelKind;
  display_name?: string;
  context_window?: number;
  max_output?: number;
  capabilities?: Partial<ModelCapabilities>;
  extras?: Record<string, unknown>;
  enabled?: boolean;
}

export interface ProviderChannelWrite {
  kind: ModelKind;
  vendor?: string;
  api_base?: string;
  full_url?: boolean;
  protocol?: LLMProtocol;
  api_key?: string;
}

export interface ProviderWrite {
  name?: string;
  enabled?: boolean;
  website_url?: string;
  notes?: string;
  channels?: ProviderChannelWrite[];
}

/** Result of the one-click recommended-vendor provisioning */
export interface VendorApplyResult {
  provider_id: number;
  name: string;
  created_provider: boolean;
  configured_kinds: ModelKind[];
}

/** Model ids offered for one channel (from the vendor descriptor or the /models endpoint) */
export interface ChannelModelCatalog {
  source: "vendor" | "remote";
  models: string[];
}

/** Agent-researched company brief (setup preview); cached per company+role+level+type+language */
export interface CompanyBrief {
  company: string;
  style: string;
  focus_areas: string[];
  process: string;
  cached: boolean;
}

/** Task bindings: default handlers for chat / stt / tts */
export interface TaskBindingInfo {
  task: "chat" | "stt" | "tts";
  profile: ModelProfile | null;
  fallback: { handler: string; mode: string };
}

export type TaskBindings = Record<"chat" | "stt" | "tts", TaskBindingInfo>;

/** Reasoning effort (only profiles with capabilities.reasoning === true) */
/** Thinking level label: the default scale is low/medium/high/max, and a
 * model may declare its own ordered variant list (extras.reasoning.variants);
 * selected labels are sent to the provider verbatim. */
export type ReasoningEffort = "low" | "medium" | "high" | "max" | (string & {});

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
