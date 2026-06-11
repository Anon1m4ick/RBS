#!/usr/bin/env bash
set -euo pipefail

TOKEN="${TOKEN:-dev-token}"
SERVER_URL="${SERVER_URL:-http://localhost:8000}"
BUILD_IMAGES=0
RUN_COMPONENT_TESTS=0
KEEP_CREATED=0
EXPECT_RUNTIME=0
INITIAL_IDS_CAPTURED=0

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

usage() {
  cat <<'EOF'
Usage: scripts/docker-e2e-tests.sh [options]

Runs Docker Compose end-to-end checks for the Oblak cloud/CDK workflow.

Options:
  --build              Build Docker images before running tests.
  --component-tests    Also run package tests and Firecracker dry-run.
  --expect-runtime     Require /run/{id} to return 200 from a configured runtime.
  --keep-created       Do not delete functions created during the test run.
  -h, --help           Show this help.

Environment:
  TOKEN                API token used by CDK and direct API checks. Default: dev-token
  SERVER_URL           Host URL for cloud-server. Default: http://localhost:8000
  PYTHON_BIN           Python executable used for JSON assertions. Default: python3
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build)
      BUILD_IMAGES=1
      shift
      ;;
    --component-tests)
      RUN_COMPONENT_TESTS=1
      shift
      ;;
    --expect-runtime)
      EXPECT_RUNTIME=1
      shift
      ;;
    --keep-created)
      KEEP_CREATED=1
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

INITIAL_IDS_FILE="$(mktemp)"
BODY_FILE="$(mktemp)"

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

api_get() {
  curl -fsS -H "Authorization: Bearer ${TOKEN}" "$SERVER_URL$1"
}

api_delete_quiet() {
  local function_id="$1"
  curl -sS -o /dev/null -X DELETE \
    -H "Authorization: Bearer ${TOKEN}" \
    "$SERVER_URL/functions/${function_id}" || true
}

store_current_function_ids() {
  api_get "/functions" | "$PYTHON_BIN" -c \
    'import json, sys; print("\n".join(str(item["id"]) for item in json.load(sys.stdin)))' \
    > "$INITIAL_IDS_FILE"
  INITIAL_IDS_CAPTURED=1
}

cleanup_created_functions() {
  local current_json new_ids
  rm -f "$BODY_FILE"

  if [[ "$KEEP_CREATED" -eq 1 ]]; then
    return
  fi

  if [[ "$INITIAL_IDS_CAPTURED" -ne 1 ]]; then
    return
  fi

  if [[ ! -s "$INITIAL_IDS_FILE" ]]; then
    : > "$INITIAL_IDS_FILE"
  fi

  current_json="$(api_get "/functions" 2>/dev/null || true)"
  if [[ -z "$current_json" ]]; then
    return
  fi

  new_ids="$("$PYTHON_BIN" -c '
import json
import pathlib
import sys

before = set(pathlib.Path(sys.argv[1]).read_text().splitlines())
for item in json.load(sys.stdin):
    function_id = str(item.get("id", ""))
    if function_id and function_id not in before:
        print(function_id)
' "$INITIAL_IDS_FILE" <<<"$current_json")"

  if [[ -z "$new_ids" ]]; then
    return
  fi

  log "Cleaning up functions created by this test run"
  while IFS= read -r function_id; do
    [[ -n "$function_id" ]] || continue
    api_delete_quiet "$function_id"
    echo "deleted $function_id"
  done <<<"$new_ids"
}

trap cleanup_created_functions EXIT

expect_status() {
  local expected_status="$1"
  local actual_status="$2"
  local label="$3"

  if [[ "$actual_status" != "$expected_status" ]]; then
    echo "Response body:" >&2
    sed -n '1,160p' "$BODY_FILE" >&2 || true
    fail "$label returned HTTP $actual_status, expected $expected_status"
  fi
}

extract_function_id_from_deploy_output() {
  grep -Eo '/run/[0-9a-fA-F-]+' | tail -n 1 | awk -F/ '{print $3}'
}

assert_function_status() {
  local function_id="$1"
  local expected_status="$2"

  api_get "/functions" | "$PYTHON_BIN" -c '
import json
import sys

expected_id = sys.argv[1]
expected_status = sys.argv[2]
items = json.load(sys.stdin)
for item in items:
    if item.get("id") == expected_id:
        actual = item.get("status")
        if actual != expected_status:
            raise SystemExit(f"{expected_id} status is {actual!r}, expected {expected_status!r}")
        print(f"{expected_id} is {expected_status}")
        break
else:
    raise SystemExit(f"{expected_id} is missing from /functions")
' "$function_id" "$expected_status"
}

test_health() {
  log "Test: cloud-server health"
  curl -fsS "$SERVER_URL/health" | "$PYTHON_BIN" -m json.tool >/dev/null
  echo "health ok"
}

wait_for_health() {
  local attempt

  log "Waiting for cloud-server health"
  for attempt in {1..60}; do
    if curl -fsS "$SERVER_URL/health" >/dev/null 2>&1; then
      return
    fi
    sleep 2
  done

  compose logs --tail=120 cloud-server >&2 || true
  fail "cloud-server did not become healthy"
}

test_auth_negative() {
  log "Test: unauthenticated /functions is rejected"
  local status
  status="$(curl -sS -o "$BODY_FILE" -w '%{http_code}' "$SERVER_URL/functions")"
  expect_status "401" "$status" "unauthenticated /functions"
  echo "401 as expected"
}

test_cdk_login() {
  log "Test: CDK login"
  printf '%s\n' "$TOKEN" | compose run --rm -T cdk login
}

test_bad_upload_negative() {
  log "Test: non-Python upload is rejected by API validation"
  local bad_file status
  bad_file="$(mktemp)"
  printf 'not python\n' > "$bad_file"

  status="$(curl -sS -o "$BODY_FILE" -w '%{http_code}' \
    -X POST \
    -H "Authorization: Bearer ${TOKEN}" \
    -F "file=@${bad_file};filename=handler.txt;type=text/plain" \
    "$SERVER_URL/functions")"
  rm -f "$bad_file"

  expect_status "400" "$status" "non-Python upload"
  grep -q 'Upload filename must end with .py' "$BODY_FILE" \
    || fail "non-Python upload did not return expected validation message"
  echo "400 as expected"
}

assert_invoke_result() {
  local label="$1"
  local status="$2"

  if [[ "$status" == "200" ]]; then
    "$PYTHON_BIN" -c '
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
runtime = payload.get("runtime")
status = payload.get("status")
if runtime != "firecracker":
    raise SystemExit(f"unexpected runtime {runtime!r}")
if status not in {"SUCCESS", "DRY_RUN"}:
    raise SystemExit(f"unexpected runtime status {status!r}")
print(f"{sys.argv[2]} returned 200 via {runtime} with status {status}")
' "$BODY_FILE" "$label"
    return
  fi

  if [[ "$status" == "501" && "$EXPECT_RUNTIME" -eq 0 ]]; then
    grep -q 'OBLAK_RUNTIME_BACKEND=firecracker' "$BODY_FILE" \
      || fail "$label returned 501 without runtime configuration message"
    echo "$label returned 501 because runtime backend is disabled"
    return
  fi

  echo "Response body:" >&2
  sed -n '1,160p' "$BODY_FILE" >&2 || true
  if [[ "$EXPECT_RUNTIME" -eq 1 ]]; then
    fail "$label returned HTTP $status, expected 200 from runtime"
  fi
  fail "$label returned unexpected HTTP $status"
}

test_positive_deploy_and_repeat_invoke() {
  log "Test: benign deploy succeeds"
  local deploy_output deploy_status function_id first_status second_status

  set +e
  deploy_output="$(compose run --rm -T cdk deploy /workspace/examples/benign/handler.py)"
  deploy_status=$?
  set -e
  echo "$deploy_output"
  if [[ "$deploy_status" -ne 0 ]]; then
    fail "benign deploy failed"
  fi

  function_id="$(printf '%s\n' "$deploy_output" | extract_function_id_from_deploy_output)"
  [[ -n "$function_id" ]] || fail "Could not parse function id from deploy output"

  assert_function_status "$function_id" "VERIFIED"

  log "Test: invoke URL is callable twice"
  first_status="$(curl -sS -o "$BODY_FILE" -w '%{http_code}' \
    -X POST \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    --data '{"name":"first"}' \
    "$SERVER_URL/run/${function_id}")"
  assert_invoke_result "first invoke" "$first_status"

  second_status="$(curl -sS -o "$BODY_FILE" -w '%{http_code}' \
    -X POST \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    --data '{"name":"second"}' \
    "$SERVER_URL/run/${function_id}")"
  assert_invoke_result "second invoke" "$second_status"
}

test_malicious_deploy_negative() {
  log "Test: malicious deploy is rejected by code verifier"
  local output status

  set +e
  output="$(compose run --rm -T cdk deploy /workspace/examples/malicious/handler.py 2>&1)"
  status=$?
  set -e

  echo "$output"
  if [[ "$status" -eq 0 ]]; then
    fail "malicious deploy unexpectedly succeeded"
  fi
  grep -q 'Verification failed' <<<"$output" \
    || fail "malicious deploy failed without verifier message"
  echo "malicious deploy rejected as expected"
}

run_component_tests() {
  log "Component tests: cloud-server"
  compose run --rm --entrypoint python cloud-server -m pytest

  log "Component tests: code-verifier"
  compose run --rm code-verifier

  log "Component tests: firecracker-runner dry-run"
  compose run --rm firecracker-runner \
    --bundle /workspace/examples/hello \
    --event-file /workspace/examples/hello/event.json \
    --function-id hello \
    --dry-run
}

main() {
  require_command docker
  require_command curl
  require_command "$PYTHON_BIN"

  if [[ ! -f cloud-server/.env ]]; then
    fail "cloud-server/.env is missing. Create it from cloud-server/env.example and set GEMINI_API_KEY."
  fi

  if [[ "$BUILD_IMAGES" -eq 1 ]]; then
    log "Building Docker images"
    compose --profile tools build
  fi

  log "Starting cloud-server"
  compose up -d cloud-server
  wait_for_health

  test_health
  test_auth_negative
  test_cdk_login
  store_current_function_ids
  test_bad_upload_negative
  test_positive_deploy_and_repeat_invoke
  test_malicious_deploy_negative

  if [[ "$RUN_COMPONENT_TESTS" -eq 1 ]]; then
    run_component_tests
  fi

  log "All Docker e2e checks passed"
}

main "$@"
