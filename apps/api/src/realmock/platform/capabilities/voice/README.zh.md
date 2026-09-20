# capabilities/voice/

语音能力层:STT / TTS 供应商适配器、语音配置、音色解析。

## `config/` — 语音配置

供应商目录(`recognize_providers.py`、`reasoning_providers.py`、`speak_providers.py`)、音色目录(`catalog.py` + `catalog_schema.py`)、凭据处理(`credentials.py`)。

## `stt/` — 语音识别

`router.py` 选择供应商;`base.py` 是适配器契约。`providers/` 下的供应商:`local`(faster-whisper)、`cloud`、`openai_compat`、`xfyun`、`aliyun`、`tencent`、`volcengine`、`baidu`、`minimax`、`json_template`(自定义厂商);`whisper.py` 承载共享的 faster-whisper 服务。

## `tts/` — 语音合成

`voice_resolve.py`(音色 / 韵律解析)、`options.py`。`providers/` 下的供应商:`edge`、`minimax`、`json_template`。
