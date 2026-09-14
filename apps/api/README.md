# RealMock API

FastAPI backend, packaged as `realmock` (src layout) and installed as an editable package.

## Run

```bash
# first time only
pip install -e ./apps/api

# start afterwards (no PYTHONPATH needed)
python -m uvicorn realmock.asgi:app --host 127.0.0.1 --port 8081
```

Keep a single worker in local development: the resume deep-review concurrency cap is counted per process, so `--workers N` multiplies it by N.

## Test

```bash
cd apps/api && pytest
```

The test layout is described in [tests/README.md](tests/README.md).

## Package layout

The `realmock` package is a modular monolith: one FastAPI process assembled from a shared platform kernel and independent business domains. See [src/realmock/README.md](src/realmock/README.md) for the map.
