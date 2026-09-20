# Documentation

Topic guides covering the whole repository. Directory-level structure lives in the READMEs next to the code (start at [README.md](../README.md)); workflow and contribution rules live in [CONTRIBUTING.md](../CONTRIBUTING.md).

| Document | Covers |
| --- | --- |
| [Architecture](architecture.md) | Modular monolith: platform / domains / bootstrap, dependency rules and guard tests, process assembly |
| [HTTP API](api.md) | Route mounting, access control, endpoints by domain, OpenAPI contract pipeline |
| [Realtime protocol](realtime_protocol.md) | Interview WebSocket: endpoint, handshake, frame format, full event vocabulary |
| [Interview flow](interview_flow.md) | Phase workflows, multi-round processes, round planning, process memory, verdict and report chain |
| [Agent system](agent_system.md) | Think-then-act loop, tools and execution isolation, context management, LLM protocol stack, model capability declarations |
| [Voice](voice.md) | STT routing and fallback, TTS providers, voice catalogs, interview room audio chain |
| [Data model](data_model.md) | The two SQLite databases, tables, migration mechanisms, runtime data location, SQLite pragmas |
| [Configuration](configuration.md) | Settings fields and environment variables, startup validation, BYOK storage, key encryption |
| [Security](security.md) | Loopback guards, session authentication, SSRF pinning, secrets at rest, key redaction, file handling |
| [Frontend](frontend.md) | Pages, feature modules, i18n, contract types, in-browser code execution, room hooks, media capture |
| [Testing](testing.md) | Backend and frontend suites, architecture and contract guard tests, CI gates |
| [Deployment](deployment.md) | CI and CD workflows, container images, runtime data volume |

Chinese versions of every guide sit beside it as `<name>.zh.md`.
