#!/usr/bin/env bash
set -euo pipefail

TOKEN="${TOKEN:-dev-token}"
SERVER_URL="${SERVER_URL:-http://localhost:8000}"
BUILD=1
RESET=0
RUN_E2E=0
TAIL_LOGS=0
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
Usage: ./deploy.sh [options]

Builds and starts the Oblak Docker workflow.

Options:
  --no-build      Start existing images without rebuilding.
  --reset         Stop containers and delete Compose volumes before starting.
  --e2e           Run scripts/docker-e2e-tests.sh after startup.
  --logs          Tail cloud-server logs after startup.
  -h, --help      Show this help.

Environment:
  TOKEN           CDK/API token. Default: dev-token
  SERVER_URL      Host URL for cloud-server. Default: http://localhost:8000
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-build)
      BUILD=0
      shift
      ;;
    --reset)
      RESET=1
      shift
      ;;
    --e2e)
      RUN_E2E=1
      shift
      ;;
    --logs)
      TAIL_LOGS=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

cd "$PROJECT_ROOT"

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

compose() {
  docker compose "$@"
}

ensure_env_file() {
  if [[ ! -f cloud-server/.env ]]; then
    log "Creating cloud-server/.env from cloud-server/env.example"
    cp cloud-server/env.example cloud-server/.env
  fi

  local gemini_api_key
  gemini_api_key="$(
    awk -F= '$1 == "GEMINI_API_KEY" { print substr($0, index($0, "=") + 1) }' cloud-server/.env | tail -n 1
  )"
  if [[ -z "$gemini_api_key" || "$gemini_api_key" == "replace-with-local-secret" ]]; then
    fail "Set GEMINI_API_KEY in cloud-server/.env before deploying."
  fi
}

wait_for_health() {
  local attempt

  log "Waiting for cloud-server health at ${SERVER_URL}/health"
  for attempt in {1..60}; do
    if curl -fsS "$SERVER_URL/health" >/dev/null 2>&1; then
      echo "cloud-server is healthy"
      return
    fi
    sleep 2
  done

  compose logs --tail=120 cloud-server >&2 || true
  fail "cloud-server did not become healthy"
}

login_cdk() {
  log "Logging in CDK container"
  printf '%s\n' "$TOKEN" | compose run --rm -T cdk login
}

main() {
  require_command docker
  require_command curl
  ensure_env_file

  if [[ "$RESET" -eq 1 ]]; then
    log "Resetting Docker Compose state"
    compose --profile tools down -v --remove-orphans
  fi

  if [[ "$BUILD" -eq 1 ]]; then
    log "Building Docker images"
    compose --profile tools build
  fi

  log "Starting cloud-server"
  compose up -d cloud-server
  wait_for_health
  login_cdk

  log "Deployment ready"
  compose ps

  cat <<EOF

Useful checks:
  scripts/docker-e2e-tests.sh
  docker compose run --rm -T cdk deploy /workspace/examples/benign/handler.py
  docker compose run --rm -T cdk list
  docker compose logs -f cloud-server
EOF

  if [[ "$RUN_E2E" -eq 1 ]]; then
    log "Running e2e tests"
    scripts/docker-e2e-tests.sh
  fi

  if [[ "$TAIL_LOGS" -eq 1 ]]; then
    log "Tailing cloud-server logs"
    compose logs -f cloud-server
  fi
}

main "$@"
