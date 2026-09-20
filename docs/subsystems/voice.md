# Voice

The voice capability layer lives in `apps/api/src/realmock/platform/capabilities/voice/`: speech-to-text adapters and routing (`stt/`), text-to-speech providers and voice resolution (`tts/`), and voice configuration catalogs (`config/`). The interview room consumes it through its realtime layer (`domains/interview/realtime/`) and the browser recorder (`apps/web/src/features/media/`).

## `stt/` — speech-to-text

`router.py` dispatches by provider id in `transcribe_with_handler()`, returning a `SttResult` (`text`, `provider`, `fallback`, `requested_provider`).

Fixed handler ids in the router table: `openai_compat`, `mimo_audio`, `local`, `xfyun`, `volcengine`, `aliyun`, `tencent`, `baidu`, `minimax`. Three additional dispatch paths cover entries without a fixed handler id:

- Full-URL endpoints select the adapter by request-path signature (`endpoint_vendors.match_vendor` over `STT_PATHS`; `minimax` is the only mapped signature) — unknown endpoints fall back to local instead of guessing a request shape.
- A user-authored adapter descriptor (`extras.stt_adapter`) routes through `JsonTemplateSttProvider`.
- A provider whose protocol is `openai_chat` with no handler id routes through `MimoAudioProvider` (audio model over the OpenAI chat protocol).

Catalog entries marked `coming_soon` (e.g. the `native_audio` entries `zhipu_glm4_voice`, `doubao_s2s`) and unknown ids fall back to local. On empty or failed results, the router falls back to `creds.fallback_handler` (default `local`) unless `fallback_mode` is `none` / `text_only`; fallback exceptions are logged, not raised.

| Module | Purpose |
| --- | --- |
| `base.py` | `SttProvider` adapter contract and `SttCredentials`. |
| `providers/whisper.py` | Shared faster-whisper service (cached model, bilingual prompt); consumed by the local provider. |
| `providers/local.py` | `LocalWhisperProvider` — local faster-whisper transcription. |
| `providers/cloud.py` | OpenAI-compatible cloud transcription service (`/v1/audio/transcriptions`) with dedicated ASR credentials; used by the OpenAI-compatible path, not a router handler id itself. |
| `providers/openai_compat.py` | `OpenAICompatProvider` and `MimoAudioProvider`. |
| `providers/xfyun.py` / `aliyun.py` / `tencent.py` / `volcengine.py` / `baidu.py` / `minimax.py` | `XfyunProvider`, `AliyunProvider`, `TencentProvider`, `VolcengineProvider`, `BaiduProvider`, `MiniMaxSttProvider`. |
| `providers/json_template.py` | `JsonTemplateSttProvider` — generic transport driven by a user-authored adapter descriptor. |

## `tts/` — text-to-speech

| Module | Purpose |
| --- | --- |
| `voice_resolve.py` | Session-level voice / prosody resolution; priority: avatar-mapped voice > credentials voice (`stage_configs` extras `tts_voice`) > default Xiaoxiao. Personality / strictness map to rate and pitch. Vendor-aware: vendors with their own voice id namespace (MiniMax) get a dedicated resolver. |
| `options.py` | Static voice catalogs (`AVATARS`, `TTS_VOICES`), e.g. `professional_male` → `zh-CN-YunyangNeural`. |
| `providers/edge.py` | Edge TTS; prosody expressed through rate/pitch with fallback to default prosody; also hosts emotion extraction and TTS text cleanup helpers. |
| `providers/minimax.py` | MiniMax T2A HTTP adapter (`POST /v1/t2a_v2`); request shape driven by the vendor descriptor (`platform/vendors/defs/minimax.json`), overridable per model entry via `extras["tts_request"]`; supports pause markers `<#x#>`. |
| `providers/json_template.py` | Generic descriptor-driven TTS transport for vendors without a dedicated adapter (descriptor in `extras["tts_adapter"]`). |

Synthesis entry: `synthesize_speech` with `TtsCredentials`, exported from the `tts` package.

## `config/` — voice configuration

`catalog.py` aggregates the three provider capability catalogs (`catalog_payload` / `find_provider`); `catalog_schema.py` holds the table schema and `_p` factory; `credentials.py` handles credentials.

| Catalog | Provider ids |
| --- | --- |
| `recognize_providers.py` | `custom`, `minimax`, `mimo_audio`, `openai_compat`, `xfyun`, `volcengine`, `aliyun`, `tencent`, `baidu`, `local`, plus `coming_soon` native-audio entries `zhipu_glm4_voice` and `doubao_s2s` |
| `reasoning_providers.py` | `custom`, `minimax`, `openai`, `deepseek`, `stepfun`, `openrouter`, `mimo`, `zhipu_glm4_voice` |
| `speak_providers.py` | `custom`, `mimo_audio`, `edge`, `minimax_speech`, `none` (subtitles only), plus `coming_soon` `zhipu_glm4_voice` and `doubao_s2s` |

At the voice package root (not under `config/`), `endpoint_vendors.py` maps full-URL endpoint path signatures to vendor ids (`STT_PATHS` / `TTS_PATHS`; `minimax` is the only mapped vendor).

## Interview room voice chain

The realtime layer (`domains/interview/realtime/`) assembles `InterviewWSHandler` from stack mixins; `MediaStackMixin` (`stacks/media_stack.py`) owns the audio path via `voice/`:

| Module | Purpose |
| --- | --- |
| `voice/pipeline.py` | STT text selection (merges browser-side preview text with ASR drafts, ASR finals win), echo detection, short-utterance TTS. |
| `voice/tts_queue.py` | `_SentenceTTSQueue` — serial sentence-level TTS queue: sentences are synthesized and played one at a time in arrival order without blocking the LLM stream; queue capped at 50 sentences, oldest dropped on overflow. |
| `engine/` | `RealtimeAudioEngine` abstraction with two implementations selected by `factory.py`: `CascadedAudioEngine` (STT → LLM → sentence TTS) and `NativeRealtimeAudioEngine` (full-duplex). |

Browser side (`apps/web/src/features/media/`):

| Piece | Purpose |
| --- | --- |
| `recorder/` | Mic capture: WebAudio capture loop (`recorderMediaGraph.ts`, AudioContext + ScriptProcessor), per-frame VAD / barge-in detection / PCM capture / silence commits (`recorderAudioFrame.ts`, thresholds in `audioRecorderConstants.ts`, e.g. `BARGE_RMS_THRESHOLD` 0.028, `BARGE_SUSTAIN_MS` 700), capture state machine (`useAudioRecorder.ts` and companion hooks). |
| `useTTSPlayer.ts` | TTS playback facade: audio unlock handling plus callback setters (speaking state, audio level, playback blocked, playback done) over `useTTSPlayerPlayback.ts`. |
