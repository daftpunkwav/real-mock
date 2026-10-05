# Backend API image (build context = repo root)
# Runtime data (DB / Chroma / uploads) lives under
# /app/apps/api/src/realmock/platform/data — mount a volume there at runtime
# and make it writable by uid 10001 (chown/chmod it on the host first).
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
# Editable install: PLATFORM_ROOT (= /app/apps/api/src/realmock/platform) then
# matches the documented volume path in the header comment.
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --retries 5 --timeout 120 --index-url "$PIP_INDEX_URL" -e ./apps/api

# Snippet sandbox: pin the linux-job backend. Auto selection only picks
# linux-job for root, so an unprivileged container would silently fall back
# to the unisolated process backend; pinning keeps the user switch, network
# namespace and cgroup controls (weaker plans degrade with explicit notes).
ENV CODEEXEC_ISOLATION=linux-job

# Run as an unprivileged user. Installed code stays root-owned (a compromised
# API process must not be able to rewrite its own modules); only the runtime
# data/upload dirs are writable by this uid. Host volumes mounted over those
# dirs must be chown'ed to 10001 on the host before use (build-time chown
# cannot change ownership of a mount).
# The linux-job sandbox needs root for its strongest plan; unprivileged it
# uses a user namespace when the runtime allows one and otherwise runs
# plainly — every unenforced control is reported in the run notes, never
# silently dropped. A writable home keeps the local Whisper model cache
# (~/.cache/huggingface) working.
RUN groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --create-home --shell /usr/sbin/nologin appuser \
    && install -d -o appuser -g appuser \
        /app/apps/api/src/realmock/platform/data \
        /app/apps/api/src/realmock/platform/uploads

USER appuser

EXPOSE 8081

CMD ["python", "-m", "uvicorn", "realmock.asgi:app", "--host", "0.0.0.0", "--port", "8081"]
