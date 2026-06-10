# Oblak Docker Workflow

This directory contains Docker wrappers for each project component:

- `cloud-server`: FastAPI upload and verification server;
- `cdk`: containerized CDK CLI used to authenticate, deploy, list, and delete functions;
- `code-verifier`: static, LLM, and antivirus verifier package test container;
- `firecracker-runner`: containerized Firecracker stage, useful for dry-runs without KVM.

## Prerequisites

- Docker with the Compose plugin.
- A Gemini API key in `cloud-server/.env`.
- Network access for image builds, Python package installation, Gemini calls, and `freshclam`.

Create the local environment file:

```powershell
cd C:\RazvojBezbednogSoftvera\RBS\project
Copy-Item cloud-server\env.example cloud-server\.env
notepad cloud-server\.env
```

Keep `cloud-server/.env` out of Git. It is already ignored.

## End-to-End Test

Run the full standardized workflow:

```powershell
cd C:\RazvojBezbednogSoftvera\RBS\project
.\scripts\e2e.ps1
```

The script performs:

1. reset Compose containers and volumes, unless `-KeepState` is passed
2. `docker compose --profile tools build`
3. `docker compose up -d cloud-server`
4. health check against `http://localhost:8000/health`
5. CDK login with `dev-token`
6. benign function deploy
7. function list
8. malicious function deploy, expected to fail
9. invoke URL check, expected to return `501`
10. CDK delete

## Manual Commands

Build everything:

```powershell
docker compose --profile tools build
```

Start the API:

```powershell
docker compose up -d cloud-server
docker compose ps
```

Inspect health and tools:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Authenticate the CDK CLI:

```powershell
"dev-token" | docker compose run --rm -T cdk login
```

Deploy a benign function:

```powershell
docker compose run --rm -T cdk deploy /workspace/examples/benign/handler.py
```

List functions:

```powershell
docker compose run --rm -T cdk list
```

Upload a malicious function and expect rejection:

```powershell
docker compose run --rm -T cdk deploy /workspace/examples/malicious/handler.py
```

Call the generated invoke URL directly:

```powershell
$headers = @{ Authorization = "Bearer dev-token" }
$functions = @(Invoke-RestMethod -Headers $headers http://localhost:8000/functions)
Invoke-RestMethod -Method Post -Headers $headers "http://localhost:8000/run/$($functions[0].id)"
```

The invoke endpoint returns `501` because runtime execution is handled by the Firecracker stage and is intentionally outside the Cloud server scope.

Delete a function:

```powershell
$id = $functions[0].id
"y" | docker compose run --rm -T cdk delete $id
```

Show server logs:

```powershell
docker compose logs -f cloud-server
```

Stop services:

```powershell
docker compose down
```

Delete all generated data:

```powershell
docker compose down -v
```

## Component Tests

Run Cloud server API tests in Docker:

```powershell
docker compose run --rm --entrypoint python cloud-server -m pytest
```

Run the verifier package tests in Docker:

```powershell
docker compose run --rm code-verifier
```

Run the Firecracker runner dry-run in Docker:

```powershell
docker compose run --rm firecracker-runner `
  --bundle /workspace/examples/hello `
  --event-file /workspace/examples/hello/event.json `
  --function-id hello `
  --dry-run
```

## Notes

- `cloud-server` installs ClamAV and can run `freshclam` at startup.
- The ClamAV database is stored in the `clamav-db` Docker volume.
- SQLite and audit logs are stored in the `cloud-data` Docker volume.
- The CDK token config is stored in the `cdk-home` Docker volume.
- Real Firecracker execution still requires a Linux host with KVM, kernel image, rootfs image, Firecracker binary, and the security setup documented in `firecracker-runner/docs/firecracker-stage.md`.
