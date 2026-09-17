/** Settings model options and draft helpers. */

import type { MessageKey } from "@/i18n";
import { DEFAULT_CONTEXT_WINDOW, DEFAULT_MAX_OUTPUT_TOKENS } from "@/lib/llmDefaults";
import type { LLMProtocol, ModelKind, ModelProfile } from "@/types";

/** settings key,Use labelKey/hintKey . */
type SettingsMessageKey = MessageKey<"settings">;

export const PROTOCOL_OPTIONS: { value: LLMProtocol; label: string }[] = [
  // .
  { value: "openai_chat", label: "OpenAI Chat Completions" },
  { value: "anthropic_messages", label: "Anthropic Messages (/v1/messages)" },
  { value: "openai_responses", label: "OpenAI Responses" },
];

/** Channel tabs: the three model types merged under one provider. */
export const KIND_META: {
  kind: ModelKind;
  labelKey: SettingsMessageKey;
  capKey: keyof ModelProfile["capabilities"];
}[] = [
  { kind: "chat", labelKey: "kinds.chat", capKey: "chat" },
  { kind: "stt", labelKey: "kinds.stt", capKey: "audio_input" },
  { kind: "tts", labelKey: "kinds.tts", capKey: "audio_output" },
];

/** Capability defaults for a new entry created under each tab. */
export const KIND_DEFAULT_CAPS: Record<
  ModelKind,
  ModelProfile["capabilities"]
> = {
  chat: { chat: true, vision: false, audio_input: false, audio_output: false, reasoning: false },
  stt: { chat: false, vision: false, audio_input: true, audio_output: false, reasoning: false },
  tts: { chat: false, vision: false, audio_input: false, audio_output: true, reasoning: false },
};

export function channelForKind(
  provider: ProviderWithModelsLike,
  kind: ModelKind,
): ProviderChannelLike | null {
  return provider.channels.find((c) => c.kind === kind) ?? null;
}

interface ProviderChannelLike {
  kind: ModelKind;
  vendor: string;
  api_base: string;
  full_url: boolean;
  protocol: LLMProtocol;
  has_api_key: boolean;
}

interface ProviderWithModelsLike {
  channels: ProviderChannelLike[];
}

export const CAP_OPTIONS: {
  key: keyof ModelProfile["capabilities"];
  labelKey: SettingsMessageKey;
}[] = [
  { key: "chat", labelKey: "caps.chat" },
  { key: "vision", labelKey: "caps.vision" },
  { key: "audio_input", labelKey: "caps.audio_input" },
  { key: "audio_output", labelKey: "caps.audio_output" },
  { key: "reasoning", labelKey: "caps.reasoning" },
];

export const TASK_META: {
  task: "chat" | "stt" | "tts";
  labelKey: SettingsMessageKey;
  hintKey: SettingsMessageKey;
  capKey: keyof ModelProfile["capabilities"];
}[] = [
  { task: "chat", labelKey: "tasks.chat.label", hintKey: "tasks.chat.hint", capKey: "chat" },
  { task: "stt", labelKey: "tasks.stt.label", hintKey: "tasks.stt.hint", capKey: "audio_input" },
  { task: "tts", labelKey: "tasks.tts.label", hintKey: "tasks.tts.hint", capKey: "audio_output" },
];

/** Press , Use */
export function modelsForTask(models: ModelProfile[], capKey: keyof ModelProfile["capabilities"]) {
  return models.filter((m) => m.capabilities?.[capKey]);
}

export function formatWindow(n: number) {
  if (!n) return "—";
  return n >= 1000 ? `${Math.round(n / 1000)}K` : String(n);
}

export interface ModelDraft {
  model: string;
  display_name: string;
  context_window: string;
  max_output: string;
  capabilities: ModelProfile["capabilities"];
  extras_text: string;
}

export function emptyDraft(kind: ModelKind): ModelDraft {
  return {
    model: "",
    display_name: "",
    context_window: String(DEFAULT_CONTEXT_WINDOW),
    max_output: String(DEFAULT_MAX_OUTPUT_TOKENS),
    capabilities: { ...KIND_DEFAULT_CAPS[kind] },
    extras_text: "",
  };
}

