# scripts/

Repository-level development and codegen scripts.

| Script | Purpose |
| --- | --- |
| `dev.sh` | One-command local startup: `start` / `stop` launches or stops the frontend and backend as background processes; logs and PIDs live in `logs/` |
| `export_openapi.py` | Export the FastAPI app's OpenAPI schema to root `openapi.json` — first half of the contract pipeline; the frontend half is `npm run generate:api-types` in `apps/web` |
| `check_no_cjk.py` | CJK policy check: reports Chinese prose outside the allowed places (web i18n catalogs, full-width punctuation glyphs in utility regexes). Run from the repo root: `python scripts/check_no_cjk.py` |
