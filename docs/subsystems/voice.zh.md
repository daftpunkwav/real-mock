# 语音

语音能力层位于 `apps/api/src/realmock/platform/capabilities/voice/`:语音识别适配器与路由(`stt/`)、语音合成供应方与音色解析(`tts/`)、语音配置目录(`config/`)。面试房经其实时层(`domains/interview/realtime/`)与浏览器采集端(`apps/web/src/features/media/`)消费该层。

## `stt/` — 语音识别

`router.py` 在 `transcribe_with_handler()` 中按 provider id 分发,返回 `SttResult`(`text`、`provider`、`fallback`、`requested_provider`)。

路由表中的固定 handler id:`openai_compat`、`mimo_audio`、`local`、`xfyun`、`volcengine`、`aliyun`、`tencent`、`baidu`、`minimax`。另有三条分发路径覆盖没有固定 handler id 的条目:

- 完整 URL 端点按请求路径签名选择适配器(`endpoint_vendors.match_vendor` 匹配 `STT_PATHS`;`minimax` 是唯一已映射的签名)— 未知端点回退本地,而不是猜测请求形状。
- 用户自编的适配器描述(`extras.stt_adapter`)经 `JsonTemplateSttProvider` 分发。
- 协议为 `openai_chat` 且无 handler id 的供应方经 `MimoAudioProvider` 分发(OpenAI chat 协议上的音频模型)。

目录中标记 `coming_soon` 的条目(如 `native_audio` 条目 `zhipu_glm4_voice`、`doubao_s2s`)与未知 id 回退本地。结果为空或失败时,路由回退到 `creds.fallback_handler`(默认 `local`),除非 `fallback_mode` 为 `none` / `text_only`;回退路径异常只记日志,不向上抛出。

| 模块 | 用途 |
| --- | --- |
| `base.py` | `SttProvider` 适配器契约与 `SttCredentials`。 |
| `providers/whisper.py` | 共享 faster-whisper 服务(模型缓存、双语 prompt);供本地供应方使用。 |
| `providers/local.py` | `LocalWhisperProvider` — 本地 faster-whisper 转写。 |
| `providers/cloud.py` | OpenAI 兼容云转写服务(`/v1/audio/transcriptions`),使用专用 ASR 凭据;供 OpenAI 兼容路径使用,本身不是路由 handler id。 |
| `providers/openai_compat.py` | `OpenAICompatProvider` 与 `MimoAudioProvider`。 |
| `providers/xfyun.py` / `aliyun.py` / `tencent.py` / `volcengine.py` / `baidu.py` / `minimax.py` | `XfyunProvider`、`AliyunProvider`、`TencentProvider`、`VolcengineProvider`、`BaiduProvider`、`MiniMaxSttProvider`。 |
| `providers/json_template.py` | `JsonTemplateSttProvider` — 由用户自编适配器描述驱动的通用传输。 |

## `tts/` — 语音合成

| 模块 | 用途 |
| --- | --- |
| `voice_resolve.py` | 会话级音色 / 韵律解析;优先级:头像映射音色 > 凭据音色(`stage_configs` extras `tts_voice`)> 默认 Xiaoxiao。personality / strictness 映射为语速与音调。具备供应方感知:拥有自己音色 id 命名空间的供应方(MiniMax)有专用解析器。 |
| `options.py` | 静态音色目录(`AVATARS`、`TTS_VOICES`),如 `professional_male` → `zh-CN-YunyangNeural`。 |
| `providers/edge.py` | Edge TTS;韵律经语速/音调表达,失败回退默认韵律;另承载情绪抽取与 TTS 文本清洗助手。 |
| `providers/minimax.py` | MiniMax T2A HTTP 适配器(`POST /v1/t2a_v2`);请求形状由供应方描述(`platform/vendors/defs/minimax.json`)驱动,可经 `extras["tts_request"]` 按模型条目覆写;支持停顿标记 `<#x#>`。 |
| `providers/json_template.py` | 面向无专用适配器供应方的通用描述驱动 TTS 传输(描述位于 `extras["tts_adapter"]`)。 |

合成入口:`synthesize_speech` 与 `TtsCredentials`,由 `tts` 包导出。

## `config/` — 语音配置

`catalog.py` 聚合三张供应方能力目录(`catalog_payload` / `find_provider`);`catalog_schema.py` 持有表结构与 `_p` 工厂;`credentials.py` 处理凭据。

| 目录 | Provider id |
| --- | --- |
| `recognize_providers.py` | `custom`、`minimax`、`mimo_audio`、`openai_compat`、`xfyun`、`volcengine`、`aliyun`、`tencent`、`baidu`、`local`,以及 `coming_soon` 的 native-audio 条目 `zhipu_glm4_voice`、`doubao_s2s` |
| `reasoning_providers.py` | `custom`、`minimax`、`openai`、`deepseek`、`stepfun`、`openrouter`、`mimo`、`zhipu_glm4_voice` |
| `speak_providers.py` | `custom`、`mimo_audio`、`edge`、`minimax_speech`、`none`(仅字幕),以及 `coming_soon` 的 `zhipu_glm4_voice`、`doubao_s2s` |

`endpoint_vendors.py` 将完整 URL 端点路径签名映射到供应方 id(`STT_PATHS` / `TTS_PATHS`;`minimax` 是唯一已映射的供应方)。

## 面试房语音链路

实时层(`domains/interview/realtime/`)以栈 mixin 组装 `InterviewWSHandler`;`MediaStack`(`stacks/media_stack.py`)经 `voice/` 持有音频路径:

| 模块 | 用途 |
| --- | --- |
| `voice/pipeline.py` | STT 文本择取(合并浏览器端预览文本与 ASR 草稿,ASR 终稿优先)、回声检测、短语句 TTS。 |
| `voice/tts_queue.py` | `_SentenceTTSQueue` — 句级串行 TTS 队列:句子按到达顺序逐句合成与播放,不阻塞 LLM 流;队列上限 50 句,溢出丢弃最旧句子。 |
| `engine/` | `RealtimeAudioEngine` 抽象,由 `factory.py` 按配置在两个实现间选择:`CascadedAudioEngine`(STT → LLM → 句级 TTS)与 `NativeRealtimeAudioEngine`(全双工)。 |

浏览器侧(`apps/web/src/features/media/`):

| 组成 | 用途 |
| --- | --- |
| `recorder/` | 麦克风采集:WebAudio 采集循环(`recorderMediaGraph.ts`,AudioContext + ScriptProcessor)、逐帧 VAD / barge-in 检测 / PCM 采集 / 静音提交(`recorderAudioFrame.ts`,阈值在 `audioRecorderConstants.ts`,如 `BARGE_RMS_THRESHOLD` 0.028、`BARGE_SUSTAIN_MS` 700),采集状态机(`useAudioRecorder.ts` 及配套 hooks)。 |
| `useTTSPlayer.ts` | TTS 播放 facade:音频解锁处理与回调设置(说话状态、音量电平、播放被阻塞、播放完成),底层为 `useTTSPlayerPlayback.ts`。 |
