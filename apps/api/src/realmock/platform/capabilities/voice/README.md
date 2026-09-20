# capabilities/voice/

Voice capability layer: STT / TTS provider adapters, voice configuration, voice resolution.

## `config/` — voice configuration

Provider catalogs (`recognize_providers.py`, `reasoning_providers.py`, `speak_providers.py`), voice catalog (`catalog.py` + `catalog_schema.py`), credential handling (`credentials.py`).

## `stt/` — speech-to-text

`router.py` selects the provider; `base.py` is the adapter contract. Providers under `providers/`: `local` (faster-whisper), `cloud`, `openai_compat`, `xfyun`, `aliyun`, `tencent`, `volcengine`, `baidu`, `minimax`, and `json_template` (user-defined vendors); `whisper.py` hosts the shared faster-whisper service.

## `tts/` — text-to-speech

`voice_resolve.py` (voice / prosody resolution), `options.py`. Providers under `providers/`: `edge`, `minimax`, `json_template`.
