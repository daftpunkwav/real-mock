# settings/

Settings domain: BYOK processor configuration, model capability registry, connectivity tests, integrations.

| Layer | Contents |
| --- | --- |
| `routes/stages.py` | Three-stage processor config: `api_base` format validation, keys encrypted at rest (AES-256-GCM), recognition credentials kept separate from the reasoning key |
| `routes/models.py` | Model-profile API: provider / channel / model / task-binding routes (capability declarations) |
| `routes/model_tests.py` | Connectivity / model tests |
| `routes/integrations.py` | Third-party integration credentials (GitHub) |
| `services/` | `model_registry.py`, `vendor_apply.py` (apply vendor descriptors), `github_integration.py`, `stage_tests.py`, `validation.py`, `route_timing.py` |

Thin domain: no `models/` or lifecycle hooks.

Tests: `apps/api/tests/settings/`.
