# apps/

Deployable applications. Each subdirectory is a self-contained app with its own toolchain and README.

| Directory | App | Role |
| --- | --- | --- |
| [`web/`](web/README.md) | RealMock web | Next.js + React frontend (dev server on port 8080) |
| [`api/`](api/README.md) | RealMock API | FastAPI backend, published as the `realmock` package (port 8081) |

Both apps run side by side in local development: `scripts/dev.sh start` from the repository root launches the two as background processes.
