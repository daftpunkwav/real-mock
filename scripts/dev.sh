#!/usr/bin/env bash
# RealMock local-dev launcher (Git Bash).
# Runs front/back in the background; stdout/stderr go to logs/; PIDs in logs/*.pid.
# Usage: scripts/dev.sh [start|stop] (default: start).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGS="$ROOT/logs"
mkdir -p "$LOGS"

BACKEND_OUT="$LOGS/backend_out.log"
BACKEND_ERR="$LOGS/backend_err.log"
FRONTEND_OUT="$LOGS/frontend_out.log"
FRONTEND_ERR="$LOGS/frontend_err.log"

start_backend() {
  # realmock-api must be installed editable first (pip install -e apps/api), then start by package name.
  cd "$ROOT"
  nohup python -m uvicorn realmock.asgi:app \
    --host 127.0.0.1 --port 8081 \
    >>"$BACKEND_OUT" 2>>"$BACKEND_ERR" &
  echo $! >"$LOGS/backend.pid"
}

start_frontend() {
  # Frontend must stay in dev mode (production can return 200 with different behavior).
  cd "$ROOT/apps/web"
  NODE_ENV=development nohup npm run dev \
    >>"$FRONTEND_OUT" 2>>"$FRONTEND_ERR" &
  echo $! >"$LOGS/frontend.pid"
}

# Resolve the listening PID by port (PID files may only record the npm/nohup shell).
pid_on_port() {
  netstat -ano | grep "LISTENING" | grep -E "[:.]$1 " | awk '{print $NF}' | head -1
}

stop() {
  local rc=0
  for port in 8081 8080; do
    local pid
    pid="$(pid_on_port "$port" || true)"
    if [ -n "$pid" ]; then
      echo "Stopping process on port $port (PID $pid)"
      taskkill //PID "$pid" //T //F || rc=1
    else
      echo "No listener on port $port"
    fi
  done
  rm -f "$LOGS/backend.pid" "$LOGS/frontend.pid"
  return $rc
}

case "${1:-start}" in
  start)
    if [ -n "$(pid_on_port 8081 || true)" ] || [ -n "$(pid_on_port 8080 || true)" ]; then
      echo "Services already listening on 8080/8081; run scripts/dev.sh stop first." >&2
      exit 1
    fi
    start_backend
    start_frontend
    echo "Backend PID $(cat "$LOGS/backend.pid") → http://127.0.0.1:8081"
    echo "Frontend PID $(cat "$LOGS/frontend.pid") → http://127.0.0.1:8080"
    echo "Logs: $LOGS"
    ;;
  stop)
    stop
    ;;
  *)
    echo "Usage: scripts/dev.sh [start|stop]" >&2
    exit 2
    ;;
esac
