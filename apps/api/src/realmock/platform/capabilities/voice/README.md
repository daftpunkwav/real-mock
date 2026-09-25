# capabilities/voice/

Voice capability layer: STT / TTS provider adapters, voice configuration, voice resolution.

## `config/` — voice configuration

Provider catalogs (`recognize_providers.py`, `reasoning_providers.py`, `speak_providers.py`), voice catalog (`catalog.py` + `catalog_schema.py`), credential handling (`credentials.py`).

## `stt/` — speech-to-text

`router.py` routes by provider id; `base.py` is the adapter contract. Fixed ids in `_PROVIDERS`: `openai_compat`, `mimo_audio`, `local` (faster-whisper), `xfyun`, `volcengine`, `aliyun`, `tencent`, `baidu`, `minimax`. Three dispatch paths bypass the table: full-URL credentials matched against `STT_PATHS` from the package-root `endpoint_vendors.py` (minimax), user-authored adapter descriptors (`json_template`), and `protocol=openai_chat` (routed to `mimo_audio`). `cloud.py` and `whisper.py` are shared service modules, not routed ids.

## `tts/` — text-to-speech

`voice_resolve.py` (voice / prosody resolution), `options.py`. Providers under `providers/`: `edge`, `minimax`, `json_template`. Full-URL credentials match `TTS_PATHS` from `endpoint_vendors.py` (minimax).
