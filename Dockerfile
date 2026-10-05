# Backend API image (build context = repo root)
# DB / Chroma / uploads live under /app/apps/api/src/realmock/platform/data — mount a volume at runtime.
FROM python:3.14-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Node.js runtime for the agent code_exec tool (javascript snippets).
# Debian trixie ships a stable Node 20.x, sufficient for snippets.
# Agent sandbox (Step 2): the linux-job backend shells out to setpriv /
# runuser / unshare, all shipped by the base distro's essential util-linux
# package, and `nobody` comes from base-passwd — so the nodejs layer below
# is the only extra apt package; the sandbox itself deliberately pulls in
# nothing further.
# Full enforcement additionally needs runtime privileges the image cannot
# grant itself: namespace creation and cgroup writes require e.g.
# `docker run --cap-add SYS_ADMIN` (or a userns-enabled runtime) plus a
# writable /sys/fs/cgroup. Without them snippets still run, and every
# unenforced control is reported back as an explicit isolation note.
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/pyproject.toml ./apps/api/pyproject.toml
COPY apps/api/src ./apps/api/src
# PIP_INDEX_URL: optional mirror for weak networks (--build-arg PIP_INDEX_URL=...); CI uses the default PyPI index.
# --retries/--timeout: large wheels (opencv, etc.) often drop on weak/proxy networks.
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --retries 5 --timeout 120 --index-url "$PIP_INDEX_URL" ./apps/api

# Run as an unprivileged user. The app persists SQLite/Chroma/uploads under its
# own package dir (platform/data), so that tree must stay writable by this uid.
# Note: the linux-job snippet sandbox needs root for its strongest plan; as this
# user it degrades to user-namespace isolation and reports it in run notes.
RUN groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser \
        "$(python -c 'import realmock, os; print(os.path.dirname(realmock.__file__))')"

USER appuser

EXPOSE 8081

CMD ["python", "-m", "uvicorn", "realmock.asgi:app", "--host", "0.0.0.0", "--port", "8081"]
