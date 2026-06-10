# Oblak Cloud Server

FastAPI server for the upload and verification part of the Oblak serverless platform.

This service implements only the requested scope:

- CDK token authentication via `GET /auth/me` and `POST /auth/login`;
- upload of one `.py` file and optional `requirements.txt` via `POST /functions`;
- storage of uploaded code and requirements in SQLite;
- verification by the `oblak-code-verifier` package, which runs Bandit, Gemini LLM analysis, and ClamAV;
- optional ClamAV scan for `requirements.txt`;
- function listing and soft deletion for the existing CDK CLI;
- audit events in SQLite and an append-only JSONL hash chain;
- a generated invoke URL whose endpoint returns `501` because execution is outside this server's scope.

## Install

```bash
cd project/cloud-server
python -m venv .venv
.venv\Scripts\activate
pip install -e ..\code-verifier
pip install -e ".[dev]"
```

ClamAV and Bandit must be available on the server. Bandit is installed by `code-verifier`; ClamAV tools are host packages:

```bash
clamscan --version
freshclam --version
```

## Configuration

The Gemini key must not be committed. Set it as an environment variable in the server process:

```powershell
$env:GEMINI_API_KEY = "<secret>"
```

Useful server variables:

| Variable | Default | Description |
| --- | --- | --- |
| `OBLAK_DATABASE_PATH` | `oblak_cloud.sqlite3` | SQLite database path |
| `OBLAK_AUDIT_LOG_PATH` | `oblak-cloud-audit.log` | JSONL audit log path |
| `OBLAK_PUBLIC_BASE_URL` | `http://localhost:8000` | Base URL used in returned invoke URLs |
| `OBLAK_BIND_HOST` | `127.0.0.1` | Host used by `oblak-cloud-server` |
| `OBLAK_BIND_PORT` | `8000` | Port used by `oblak-cloud-server` |
| `OBLAK_BOOTSTRAP_USERNAME` | unset | Optional startup user |
| `OBLAK_BOOTSTRAP_TOKEN` | unset | Optional startup API token |
| `OBLAK_RUN_FRESHCLAM_ON_STARTUP` | `false` | Run `freshclam` on startup |

Create a user:

```bash
oblak-cloud-create-user alice "dev-token"
```

Or bootstrap one on startup:

```powershell
$env:OBLAK_BOOTSTRAP_USERNAME = "alice"
$env:OBLAK_BOOTSTRAP_TOKEN = "dev-token"
```

## Run

```bash
uvicorn oblak_server.main:app --reload
```

In another terminal:

```bash
$env:OBLAK_SERVER_URL = "http://localhost:8000"
cd ..\cdk-cli
pip install -e .
cdk login
cdk deploy path\to\handler.py
cdk list
```

## API

`POST /functions` expects multipart form fields:

- `file`: required `.py` file;
- `requirements`: optional `requirements.txt`.

Successful response:

```json
{
  "function_id": "uuid",
  "id": "uuid",
  "name": "handler.py",
  "status": "VERIFIED",
  "invoke_url": "http://localhost:8000/run/uuid"
}
```

`POST /run/{function_id}` is intentionally a placeholder and returns `501`.

## Tests

```bash
cd project/cloud-server
pytest
```

The API tests mock the verifier so they do not call Gemini, Bandit, or ClamAV.

## Docker Workflow

From `project/`, create a local ignored environment file:

```powershell
Copy-Item cloud-server\env.example cloud-server\.env
notepad cloud-server\.env
```

Set `GEMINI_API_KEY` in `cloud-server\.env`. The default Docker auth user is:

```text
username: alice
token: dev-token
```

Build and start the API server:

```powershell
cd C:\RazvojBezbednogSoftvera\RBS\project
docker compose --profile tools build
docker compose up -d cloud-server
docker compose ps
```

Check health:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Authenticate the containerized CDK CLI:

```powershell
"dev-token" | docker compose run --rm -T cdk login
```

Deploy the benign function:

```powershell
docker compose run --rm -T cdk deploy /workspace/examples/benign/handler.py
```

List deployed functions:

```powershell
docker compose run --rm -T cdk list
```

Verify a malicious upload is rejected:

```powershell
docker compose run --rm -T cdk deploy /workspace/examples/malicious/handler.py
```

The malicious command should exit non-zero with a verification error.

Run the standardized PowerShell e2e workflow:

```powershell
.\scripts\e2e.ps1
```

The script resets Compose volumes by default. Use `.\scripts\e2e.ps1 -KeepState` to reuse the current Docker state.

Run API unit tests inside the Cloud server image:

```powershell
docker compose run --rm --entrypoint python cloud-server -m pytest
```

Run the verifier package tests inside its own container:

```powershell
docker compose run --rm code-verifier
```

Run the Firecracker stage in containerized dry-run mode:

```powershell
docker compose run --rm firecracker-runner `
  --bundle /workspace/examples/hello `
  --event-file /workspace/examples/hello/event.json `
  --function-id hello `
  --dry-run
```

Stop the application:

```powershell
docker compose down
```

Reset all Docker volumes, including SQLite data, CDK auth config, ClamAV DB, and Firecracker dry-run output:

```powershell
docker compose down -v
```
