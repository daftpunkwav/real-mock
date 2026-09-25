# capabilities/voice/

语音能力层:STT / TTS 供应商适配器、语音配置、音色解析。

## `config/` — 语音配置

供应商目录(`recognize_providers.py`、`reasoning_providers.py`、`speak_providers.py`)、音色目录(`catalog.py` + `catalog_schema.py`)、凭据处理(`credentials.py`)。

## `stt/` — 语音识别

`router.py` 按 provider id 路由;`base.py` 是适配器契约。`_PROVIDERS` 固定表:`openai_compat`、`mimo_audio`、`local`(faster-whisper)、`xfyun`、`volcengine`、`aliyun`、`tencent`、`baidu`、`minimax`。三条分发路径绕过该表:full-URL 凭据按包根 `endpoint_vendors.py` 的 `STT_PATHS` 匹配(minimax)、用户自定义适配器描述(`json_template`)、`protocol=openai_chat`(路由到 `mimo_audio`)。`cloud.py` 与 `whisper.py` 是共享服务模块,不是路由 id。

## `tts/` — 语音合成

`voice_resolve.py`(音色 / 韵律解析)、`options.py`。`providers/` 下的供应商:`edge`、`minimax`、`json_template`。full-URL 凭据按 `endpoint_vendors.py` 的 `TTS_PATHS` 匹配(minimax)。
