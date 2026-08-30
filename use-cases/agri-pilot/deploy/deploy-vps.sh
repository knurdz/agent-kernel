#!/usr/bin/env bash
# AgriPilot VPS deployment helper for Ubuntu 22.04/24.04.
# Idempotent: safe to rerun; never deletes named volumes or overwrites a populated env file.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEPLOY_DIR="${SCRIPT_DIR}"
ENV_FILE="${DEPLOY_DIR}/.env.production"
COMPOSE_FILE="${DEPLOY_DIR}/docker-compose.vps.yml"
STATE_DIR="${DEPLOY_DIR}/.deploy-state"
BACKUP_DIR="${DEPLOY_DIR}/backups"
LOCK_FILE="${STATE_DIR}/deploy.lock"
LAST_SHA_FILE="${STATE_DIR}/last-successful-sha"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-agripilot-vps}"

export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

log() { printf '[agripilot] %s\n' "$*"; }
warn() { printf '[agripilot] WARN: %s\n' "$*" >&2; }
die() { printf '[agripilot] ERROR: %s\n' "$*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

urlencode() {
  local value="$1"
  python3 -c 'import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1], safe=""))' "${value}"
}

export_compose_db_url_vars() {
  export POSTGRES_USER_ENCODED="$(urlencode "${POSTGRES_USER}")"
  export POSTGRES_PASSWORD_ENCODED="$(urlencode "${POSTGRES_PASSWORD}")"
  export POSTGRES_DB="${POSTGRES_DB:-agripilot}"
}

compose() {
  docker compose -p "${COMPOSE_PROJECT_NAME}" -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" "$@"
}

load_env() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    die "Missing ${ENV_FILE}. Copy deploy/.env.production.example and fill values, or run: $0 setup"
  fi
  require_cmd python3
  # shellcheck disable=SC1090
  set -a
  source "${ENV_FILE}"
  set +a
  export_compose_db_url_vars
}

random_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    tr -dc 'A-Za-z0-9' </dev/urandom | head -c 48
  fi
}

is_placeholder() {
  local value="$1"
  [[ -z "${value}" ]] && return 0
  [[ "${value}" == CHANGE_ME* ]] && return 0
  [[ "${value}" == *example.com* ]] && return 0
  [[ "${value}" == your_* ]] && return 0
  return 1
}

acquire_lock() {
  mkdir -p "${STATE_DIR}"
  if [[ -f "${LOCK_FILE}" ]]; then
    local pid
    pid="$(cat "${LOCK_FILE}" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      die "Another deployment is running (pid ${pid})."
    fi
    warn "Removing stale lock."
  fi
  echo "$$" >"${LOCK_FILE}"
}

release_lock() {
  rm -f "${LOCK_FILE}"
}

on_exit() {
  local code=$?
  release_lock || true
  if [[ ${code} -ne 0 ]]; then
    show_failure_diagnostics || true
  fi
}
trap on_exit EXIT

ensure_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    return 0
  fi
  log "Installing Docker Engine and Compose plugin..."
  require_cmd curl
  curl -fsSL https://get.docker.com | sh
  require_cmd docker
  docker compose version >/dev/null 2>&1 || die "Docker Compose plugin unavailable after install."
}

ensure_git() {
  if command -v git >/dev/null 2>&1; then
    return 0
  fi
  log "Installing git..."
  require_cmd apt-get
  sudo apt-get update -qq
  sudo apt-get install -y git
}

check_ports_free() {
  if compose ps --status running --services 2>/dev/null | grep -qx caddy; then
    log "Existing Caddy container detected; skipping port 80/443 availability check."
    return 0
  fi
  local port
  for port in 80 443; do
    if command -v ss >/dev/null 2>&1; then
      if ss -ltn "( sport = :${port} )" | grep -q ":${port}"; then
        die "Port ${port} is already in use. Stop the conflicting service before deploying."
      fi
    elif command -v lsof >/dev/null 2>&1; then
      if lsof -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
        die "Port ${port} is already in use. Stop the conflicting service before deploying."
      fi
    fi
  done
}

validate_env() {
  load_env

  [[ -n "${DOMAIN:-}" ]] || die "DOMAIN is required in ${ENV_FILE}"
  is_placeholder "${DOMAIN}" && die "DOMAIN still looks like a placeholder."

  [[ -n "${POSTGRES_USER:-}" ]] || die "POSTGRES_USER is required."
  [[ -n "${POSTGRES_PASSWORD:-}" ]] || die "POSTGRES_PASSWORD is required."
  is_placeholder "${POSTGRES_PASSWORD}" && die "POSTGRES_PASSWORD still looks like a placeholder."
  ((${#POSTGRES_PASSWORD} >= 16)) || die "POSTGRES_PASSWORD must be at least 16 characters."

  [[ -n "${AK_MARKETPLACE__JWT_SECRET:-}" ]] || die "AK_MARKETPLACE__JWT_SECRET is required."
  is_placeholder "${AK_MARKETPLACE__JWT_SECRET}" && die "AK_MARKETPLACE__JWT_SECRET still looks like a placeholder."
  ((${#AK_MARKETPLACE__JWT_SECRET} >= 32)) || die "AK_MARKETPLACE__JWT_SECRET must be at least 32 characters."

  if [[ -z "${OPENAI_API_KEY:-}" && -z "${GEMINI_API_KEY:-}" && -z "${OPENROUTER_API_KEY:-}" ]]; then
    die "Set at least one LLM provider key (OPENAI_API_KEY, GEMINI_API_KEY, or OPENROUTER_API_KEY)."
  fi

  for var in AK_WHATSAPP__VERIFY_TOKEN AK_WHATSAPP__ACCESS_TOKEN AK_WHATSAPP__PHONE_NUMBER_ID \
    AK_TELEGRAM__BOT_TOKEN AK_TELEGRAM__WEBHOOK_SECRET; do
    [[ -n "${!var:-}" ]] || die "${var} is required for production."
    is_placeholder "${!var}" && die "${var} still looks like a placeholder."
  done

  if [[ "${AK_NOTIFICATIONS__FCM_ENABLED:-false}" == "true" ]]; then
    local cred_path="${AK_NOTIFICATIONS__FIREBASE_CREDENTIALS_PATH:-}"
    [[ -n "${cred_path}" ]] || die "AK_NOTIFICATIONS__FIREBASE_CREDENTIALS_PATH is required when FCM is enabled."
    [[ -f "${cred_path}" ]] || die "Firebase credentials file not found: ${cred_path}"
  fi

  if [[ -n "${AK_MARKETPLACE__DATABASE_URL:-}" ]]; then
    warn "AK_MARKETPLACE__DATABASE_URL in ${ENV_FILE} is ignored; Compose builds the internal db URL from POSTGRES_*."
  fi

  compose config >/dev/null
}

setup_env_interactive() {
  if [[ -f "${ENV_FILE}" ]]; then
    die "${ENV_FILE} already exists. Edit it manually or remove it before interactive setup."
  fi
  cp "${DEPLOY_DIR}/.env.production.example" "${ENV_FILE}"
  chmod 600 "${ENV_FILE}"

  log "Interactive first-time setup (secrets are written to ${ENV_FILE}; values are not printed)."

  read -r -p "Public domain (e.g. agripilot.example.com): " domain
  read -r -p "ACME email for Let's Encrypt [optional]: " acme_email

  local jwt_secret postgres_password whatsapp_verify telegram_secret
  jwt_secret="$(random_secret)$(random_secret | head -c 8)"
  postgres_password="$(random_secret)"
  whatsapp_verify="$(random_secret | head -c 24)"
  telegram_secret="$(random_secret | head -c 32)"

  sed -i "s|^DOMAIN=.*|DOMAIN=${domain}|" "${ENV_FILE}"
  sed -i "s|^ACME_EMAIL=.*|ACME_EMAIL=${acme_email}|" "${ENV_FILE}"
  sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${postgres_password}|" "${ENV_FILE}"
  sed -i "s|^AK_MARKETPLACE__JWT_SECRET=.*|AK_MARKETPLACE__JWT_SECRET=${jwt_secret}|" "${ENV_FILE}"
  sed -i "s|^AK_WHATSAPP__VERIFY_TOKEN=.*|AK_WHATSAPP__VERIFY_TOKEN=${whatsapp_verify}|" "${ENV_FILE}"
  sed -i "s|^AK_TELEGRAM__WEBHOOK_SECRET=.*|AK_TELEGRAM__WEBHOOK_SECRET=${telegram_secret}|" "${ENV_FILE}"

  log "Generated JWT, Postgres, WhatsApp verify, and Telegram webhook secrets."
  log "Edit ${ENV_FILE} to add LLM, WhatsApp, and Telegram bot credentials before deploying."
}

git_update() {
  if [[ "${DEPLOY_SKIP_GIT:-0}" == "1" ]]; then
    warn "DEPLOY_SKIP_GIT=1 — skipping git fetch/pull (deploying current tree on disk)."
    return 0
  fi
  cd "${REPO_ROOT}"
  if [[ ! -d .git ]]; then
    die "Not a git repository: ${REPO_ROOT}"
  fi
  if ! git diff --quiet || ! git diff --cached --quiet; then
    die "Git worktree is dirty. Commit or stash changes before deploying, or set DEPLOY_SKIP_GIT=1 to deploy the current tree."
  fi
  local branch="${BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"
  log "Fetching and fast-forwarding branch ${branch}..."
  git fetch --prune origin "${branch}" 2>/dev/null || git fetch --prune
  git checkout "${branch}"
  git pull --ff-only origin "${branch}" 2>/dev/null || git pull --ff-only
}

bootstrap_clone() {
  : "${REPO_URL:?REPO_URL is required for bootstrap}"
  : "${INSTALL_DIR:?INSTALL_DIR is required for bootstrap}"
  : "${BRANCH:=main}"

  ensure_git
  ensure_docker

  if [[ -d "${INSTALL_DIR}/.git" ]]; then
    REPO_ROOT="${INSTALL_DIR}/use-cases/agri-pilot"
    if [[ ! -d "${REPO_ROOT}" ]]; then
      REPO_ROOT="${INSTALL_DIR}"
    fi
    DEPLOY_DIR="${REPO_ROOT}/deploy"
    ENV_FILE="${DEPLOY_DIR}/.env.production"
    COMPOSE_FILE="${DEPLOY_DIR}/docker-compose.vps.yml"
    STATE_DIR="${DEPLOY_DIR}/.deploy-state"
    BACKUP_DIR="${DEPLOY_DIR}/backups"
    LOCK_FILE="${STATE_DIR}/deploy.lock"
    LAST_SHA_FILE="${STATE_DIR}/last-successful-sha"
    cd "${REPO_ROOT}"
    git_update
    return 0
  fi

  log "Cloning ${REPO_URL} (branch ${BRANCH}) into ${INSTALL_DIR}..."
  sudo mkdir -p "$(dirname "${INSTALL_DIR}")"
  sudo git clone --branch "${BRANCH}" --depth 1 "${REPO_URL}" "${INSTALL_DIR}"
  sudo chown -R "${USER}:${USER}" "${INSTALL_DIR}"

  if [[ -d "${INSTALL_DIR}/use-cases/agri-pilot" ]]; then
    REPO_ROOT="${INSTALL_DIR}/use-cases/agri-pilot"
  else
    REPO_ROOT="${INSTALL_DIR}"
  fi
  DEPLOY_DIR="${REPO_ROOT}/deploy"
  ENV_FILE="${DEPLOY_DIR}/.env.production"
  COMPOSE_FILE="${DEPLOY_DIR}/docker-compose.vps.yml"
  STATE_DIR="${DEPLOY_DIR}/.deploy-state"
  BACKUP_DIR="${DEPLOY_DIR}/backups"
  LOCK_FILE="${STATE_DIR}/deploy.lock"
  LAST_SHA_FILE="${STATE_DIR}/last-successful-sha"
}

wait_for_service_healthy() {
  local service="$1"
  local attempts="${2:-60}"
  local i
  for ((i = 1; i <= attempts; i++)); do
    local cid status
    cid="$(compose ps -q "${service}" 2>/dev/null || true)"
    [[ -n "${cid}" ]] || { sleep 2; continue; }
    status="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${cid}" 2>/dev/null || echo starting)"
    if [[ "${status}" == "healthy" || "${status}" == "running" ]]; then
      if [[ "${service}" == "migrate" ]]; then
        if docker inspect --format='{{.State.Status}}' "${cid}" 2>/dev/null | grep -q exited; then
          local exit_code
          exit_code="$(docker inspect --format='{{.State.ExitCode}}' "${cid}")"
          [[ "${exit_code}" == "0" ]] && return 0
          die "Migration container exited with code ${exit_code}."
        fi
      else
        [[ "${status}" == "healthy" ]] && return 0
      fi
    fi
    sleep 5
  done
  die "Timed out waiting for ${service} to become healthy."
}

probe_public_health() {
  local url="https://${DOMAIN}/health"
  local attempts="${1:-30}"
  local i
  log "Probing ${url} ..."
  for ((i = 1; i <= attempts; i++)); do
    if curl -fsS --max-time 10 "${url}" >/dev/null 2>&1; then
      log "Public health check OK."
      return 0
    fi
    sleep 10
  done
  return 1
}

register_telegram_webhook() {
  load_env
  [[ -n "${AK_TELEGRAM__BOT_TOKEN:-}" ]] || return 0
  local webhook_url="https://${DOMAIN}/telegram/webhook"
  log "Registering Telegram webhook..."
  local response
  response="$(curl -fsS --max-time 20 \
    "https://api.telegram.org/bot${AK_TELEGRAM__BOT_TOKEN}/setWebhook" \
    --data-urlencode "url=${webhook_url}" \
    --data-urlencode "secret_token=${AK_TELEGRAM__WEBHOOK_SECRET}")" || die "Telegram setWebhook request failed."
  echo "${response}" | grep -q '"ok":true' || die "Telegram setWebhook returned failure: ${response}"

  local info
  info="$(curl -fsS --max-time 20 "https://api.telegram.org/bot${AK_TELEGRAM__BOT_TOKEN}/getWebhookInfo")" || true
  log "Telegram getWebhookInfo: ${info}"
}

print_whatsapp_instructions() {
  load_env
  cat <<EOF

WhatsApp Meta console configuration (manual):
  Callback URL: https://${DOMAIN}/whatsapp/webhook
  Verify token: (value of AK_WHATSAPP__VERIFY_TOKEN in ${ENV_FILE})
  Subscribe to: messages

EOF
}

sync_postgres_password() {
  log "Ensuring Postgres role password matches ${ENV_FILE} ..."
  local sql
  sql="$(POSTGRES_USER="${POSTGRES_USER}" POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" python3 - <<PY
import os

user = os.environ["POSTGRES_USER"]
password = os.environ["POSTGRES_PASSWORD"]
print('ALTER USER "{}" WITH PASSWORD {};'.format(user, repr(password)))
PY
)"
  compose exec -T db psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${POSTGRES_DB:-agripilot}" -c "${sql}"
}

show_failure_diagnostics() {
  warn "Deployment failed. Recent service status:"
  compose ps || true
  if compose logs --tail=200 db 2>/dev/null | grep -q "password authentication failed for user"; then
    warn "Postgres rejected the app/migrate password."
    warn "This usually means POSTGRES_PASSWORD in ${ENV_FILE} was changed after the db volume was first created."
    warn "Fix: pull latest deploy script (auto-syncs password), or run:"
    warn "  ./deploy/deploy-vps.sh sync-db-password"
    warn "Or reset the empty database volume:"
    warn "  docker compose -p ${COMPOSE_PROJECT_NAME} -f ${COMPOSE_FILE} --env-file ${ENV_FILE} down"
    warn "  docker volume rm ${COMPOSE_PROJECT_NAME}_pgdata"
    warn "  ./deploy/deploy-vps.sh deploy"
  fi
  warn "Recent logs (last 80 lines per service):"
  for svc in db redis migrate app caddy; do
    warn "--- ${svc} ---"
    compose logs --tail=80 "${svc}" 2>/dev/null || true
  done
  if [[ -f "${LAST_SHA_FILE}" ]]; then
    warn "Last successful Git SHA: $(cat "${LAST_SHA_FILE}")"
    warn "To inspect that revision: git checkout $(cat "${LAST_SHA_FILE}")"
    warn "Database was NOT rolled back automatically. Fix forward or restore from backup."
  fi
}

verify_plant_schema() {
  log "Verifying plant tracking migration..."
  compose exec -T db psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${POSTGRES_DB:-agripilot}" -tAc \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('plants','plant_observations');" \
    | grep -qx '2' || die "Plant tracking tables missing after migration. Check migrate logs."
}

verify_plant_media() {
  log "Verifying plant photo storage..."
  compose exec -T app python -c \
    "from marketplace.plant_media import media_root; p=media_root(); assert p.is_dir(), p; print('plant media:', p)" \
    || die "Plant media directory is not writable. Check the plant-media volume mount."
}

print_post_deploy_notes() {
  cat <<EOF

Deploy notes:
  - Plant tracking API is live (/api/farmer/scans, /api/farmer/plants*, buyer listing insights).
  - Observation photos persist in Docker volume: ${COMPOSE_PROJECT_NAME}_plant-media
  - Rebuild the mobile APK with: flutter build apk --release --dart-define=API_BASE_URL=https://${DOMAIN}
  - Postgres backups do not include plant photos; archive the plant-media volume separately if needed.

EOF
}

cmd_deploy() {
  acquire_lock
  require_cmd docker
  require_cmd curl
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 plugin is required."

  if [[ -n "${REPO_URL:-}" ]]; then
    bootstrap_clone
  else
    cd "${REPO_ROOT}"
    if [[ -d .git ]]; then
      git_update
    fi
  fi

  if [[ ! -f "${ENV_FILE}" ]]; then
    setup_env_interactive
    die "Finish editing ${ENV_FILE}, then rerun: $0 deploy"
  fi

  validate_env
  check_ports_free

  local previous_sha=""
  [[ -f "${LAST_SHA_FILE}" ]] && previous_sha="$(cat "${LAST_SHA_FILE}")"
  local current_sha=""
  if [[ -d "${REPO_ROOT}/.git" ]]; then
    current_sha="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
  fi

  log "Pulling base images..."
  compose pull db redis caddy || true

  log "Building application image..."
  compose build app

  log "Starting database and Redis..."
  compose up -d db redis
  wait_for_service_healthy db

  sync_postgres_password

  log "Running database migrations..."
  compose run --rm migrate
  local migrate_exit=$?
  if [[ ${migrate_exit} -ne 0 ]]; then
    die "Migration failed with exit code ${migrate_exit}."
  fi
  verify_plant_schema

  log "Starting application and Caddy..."
  compose up -d app caddy
  wait_for_service_healthy app 90
  verify_plant_media

  if ! probe_public_health 30; then
    warn "Public HTTPS health check failed."
    [[ -n "${previous_sha}" ]] && warn "Previous successful SHA: ${previous_sha}"
    die "Deploy finished but https://${DOMAIN}/health is not reachable yet."
  fi

  register_telegram_webhook
  print_whatsapp_instructions

  if [[ -n "${current_sha}" ]]; then
    mkdir -p "${STATE_DIR}"
    echo "${current_sha}" >"${LAST_SHA_FILE}"
  fi
  print_post_deploy_notes
  log "Deployment successful."
}

cmd_update() {
  log "Updating AgriPilot on this server (pull, rebuild, migrate, restart)..."
  cmd_deploy "$@"
}

cmd_status() {
  load_env
  compose ps
  if [[ -f "${LAST_SHA_FILE}" ]]; then
    log "Last successful Git SHA: $(cat "${LAST_SHA_FILE}")"
  fi
  probe_public_health 3 || warn "Public health endpoint is not reachable."
}

cmd_logs() {
  load_env
  local service="${1:-}"
  if [[ -n "${service}" ]]; then
    compose logs -f --tail=200 "${service}"
  else
    compose logs -f --tail=200
  fi
}

cmd_restart() {
  load_env
  compose restart app caddy
  wait_for_service_healthy app 60
  probe_public_health 10 || die "Restart completed but public health check failed."
  log "Restart successful."
}

cmd_backup() {
  load_env
  mkdir -p "${BACKUP_DIR}"
  chmod 700 "${BACKUP_DIR}"
  local ts manifest dump
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  dump="${BACKUP_DIR}/postgres-${ts}.sql.gz"
  manifest="${BACKUP_DIR}/manifest-${ts}.json"

  log "Creating Postgres backup ${dump} ..."
  compose exec -T db pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB:-agripilot}" | gzip >"${dump}"
  chmod 600 "${dump}"

  local sha image_id
  sha="$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || echo unknown)"
  image_id="$(compose images -q app 2>/dev/null | head -n1 || echo unknown)"

  cat >"${manifest}" <<EOF
{
  "timestamp": "${ts}",
  "git_sha": "${sha}",
  "domain": "${DOMAIN}",
  "postgres_dump": "$(basename "${dump}")",
  "plant_media_volume": "${COMPOSE_PROJECT_NAME}_plant-media",
  "app_image_id": "${image_id}",
  "compose_project": "${COMPOSE_PROJECT_NAME}"
}
EOF
  chmod 600 "${manifest}"
  log "Backup complete: ${dump}"
  log "Manifest: ${manifest}"
}

cmd_restore() {
  local archive="${1:-}"
  [[ -n "${archive}" ]] || die "Usage: $0 restore <backup.sql.gz>"
  [[ -f "${archive}" ]] || die "Backup file not found: ${archive}"

  load_env
  read -r -p "Restore Postgres from ${archive}? This OVERWRITES the current database. Type 'restore' to continue: " confirm
  [[ "${confirm}" == "restore" ]] || die "Restore cancelled."

  log "Restoring Postgres from ${archive} ..."
  compose up -d db
  wait_for_service_healthy db
  gunzip -c "${archive}" | compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB:-agripilot}"
  log "Restore complete. Consider restarting the app: $0 restart"
}

cmd_sync_db_password() {
  load_env
  compose up -d db
  wait_for_service_healthy db
  sync_postgres_password
  log "Postgres password synced from ${ENV_FILE}."
}

cmd_validate() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    ENV_FILE="${DEPLOY_DIR}/env.smoke.example"
  fi
  compose config >/dev/null
  log "Compose configuration is valid."
}

usage() {
  cat <<EOF
Usage: $0 [command]

Commands:
  deploy    Build, migrate, start stack, verify HTTPS /health (default)
  update    Same as deploy — use on the VPS after git pull to roll out changes
  setup     Interactive first-time ${ENV_FILE} creation
  status    Show service status and probe public health
  logs      Follow logs (optional service: db|redis|migrate|app|caddy)
  restart   Restart app and Caddy
  backup    Timestamped Postgres dump under deploy/backups/
  restore   Restore Postgres from a .sql.gz backup (destructive; requires confirmation)
  sync-db-password  Align Postgres role password with POSTGRES_PASSWORD in ${ENV_FILE}
  validate  Validate merged Compose config

Bootstrap env vars (fresh VPS):
  REPO_URL=https://github.com/your-org/agent-kernel.git
  BRANCH=main
  INSTALL_DIR=/opt/agent-kernel

Server update env vars:
  DEPLOY_SKIP_GIT=1   Deploy the current checkout without git pull (e.g. rsync'd tree)
  BRANCH=main         Git branch to fast-forward when pulling (default: current branch)

EOF
}

main() {
  local cmd="${1:-deploy}"
  shift || true
  case "${cmd}" in
    deploy) cmd_deploy "$@" ;;
    update) cmd_update "$@" ;;
    setup) setup_env_interactive ;;
    status) cmd_status "$@" ;;
    logs) cmd_logs "$@" ;;
    restart) cmd_restart "$@" ;;
    backup) cmd_backup "$@" ;;
    restore) cmd_restore "$@" ;;
    sync-db-password) cmd_sync_db_password "$@" ;;
    validate) cmd_validate "$@" ;;
    -h | --help | help) usage ;;
    *) die "Unknown command: ${cmd}. Run $0 --help" ;;
  esac
}

main "$@"
