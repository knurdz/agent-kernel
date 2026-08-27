#!/usr/bin/env bash
# Static checks + optional local smoke test for the VPS deployment stack.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${SCRIPT_DIR}/env.smoke.example"
COMPOSE_VPS="${SCRIPT_DIR}/docker-compose.vps.yml"
COMPOSE_SMOKE="${SCRIPT_DIR}/docker-compose.smoke.yml"
DEPLOY_SCRIPT="${SCRIPT_DIR}/deploy-vps.sh"

log() { printf '[validate-deploy] %s\n' "$*"; }
die() { printf '[validate-deploy] ERROR: %s\n' "$*" >&2; exit 1; }

log "Checking deploy-vps.sh syntax..."
bash -n "${DEPLOY_SCRIPT}"

if command -v shellcheck >/dev/null 2>&1; then
  log "Running ShellCheck on deploy-vps.sh..."
  shellcheck -x "${DEPLOY_SCRIPT}"
else
  log "ShellCheck not installed; skipping."
fi

log "Validating production compose config with smoke fixture env..."
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  # shellcheck disable=SC1090
  set -a
  source "${ENV_FILE}"
  set +a
  export POSTGRES_USER_ENCODED="$(python3 -c 'import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1], safe=""))' "${POSTGRES_USER}")"
  export POSTGRES_PASSWORD_ENCODED="$(python3 -c 'import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1], safe=""))' "${POSTGRES_PASSWORD}")"
  docker compose -f "${COMPOSE_VPS}" --env-file "${ENV_FILE}" config >/dev/null
  log "Validating smoke override merge..."
  docker compose -f "${COMPOSE_VPS}" -f "${COMPOSE_SMOKE}" --env-file "${ENV_FILE}" config >/dev/null
else
  log "Docker not available; skipping compose config validation."
fi

if [[ "${1:-}" == "--smoke" ]]; then
  require_cmd() { command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"; }
  require_cmd docker
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 required for smoke test."

  # shellcheck disable=SC1090
  set -a
  source "${ENV_FILE}"
  set +a
  export POSTGRES_USER_ENCODED="$(python3 -c 'import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1], safe=""))' "${POSTGRES_USER}")"
  export POSTGRES_PASSWORD_ENCODED="$(python3 -c 'import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1], safe=""))' "${POSTGRES_PASSWORD}")"

  cd "${REPO_ROOT}"
  local_project="agripilot-smoke-$$"
  compose() {
    docker compose -p "${local_project}" -f "${COMPOSE_VPS}" -f "${COMPOSE_SMOKE}" --env-file "${ENV_FILE}" "$@"
  }

  cleanup() {
    compose down --remove-orphans >/dev/null 2>&1 || true
  }
  trap cleanup EXIT

  log "Building app image..."
  compose build app migrate

  log "Starting db + redis..."
  compose up -d db redis
  for _ in $(seq 1 30); do
    compose exec -T db pg_isready -U "${POSTGRES_USER}" >/dev/null 2>&1 && break
    sleep 2
  done

  log "Running migrations..."
  compose run --rm migrate

  log "Starting app (no Caddy)..."
  compose up -d app

  port="${SMOKE_APP_PORT:-18000}"
  for _ in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
      log "Smoke test passed: http://127.0.0.1:${port}/health"
      exit 0
    fi
    sleep 3
  done
  die "Smoke test failed: app health endpoint did not become ready."
fi

log "Validation complete. Run with --smoke to build and exercise the stack locally."
