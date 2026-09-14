# features/

Feature-first business modules. Each feature owns its components, hooks, and tests; cross-feature pieces go up to `src/components/` and `src/lib/`.

| Feature | Purpose |
| --- | --- |
| `home/` | Landing page |
| `profile/` | Candidate profile editor |
| `resume/` | Resume upload, review, paginated preview |
| `settings/` | Settings pages (providers, models, stages, integrations) |
| `prep/` | Prep coach chat UI (composer, context panel, slash commands) |
| `interview/` | Interview room; the room hook assembly has its own README in [interview/hooks/room/](interview/hooks/room/README.md) |
| `report/` | Report display (tabs, score formatting, live events) |
| `history/` | Interview history page |
| `growth/` | Growth statistics page |
| `media/` | Shared media primitives: mic recorder, TTS player |
| `avatar/` | Interviewer avatar rendering (stage, portraits, scenes) |
