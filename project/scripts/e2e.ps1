param(
    [string]$Token = "dev-token",
    [switch]$KeepState
)

$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $projectRoot

if (-not $KeepState) {
    Write-Host "Resetting previous Docker state..."
    docker compose --profile tools down -v --remove-orphans
}

Write-Host "Building containers..."
docker compose --profile tools build

Write-Host "Starting cloud-server..."
docker compose up -d cloud-server

Write-Host "Waiting for /health..."
for ($i = 0; $i -lt 60; $i++) {
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 2
        if ($health.ok -eq $true) {
            break
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}

if ($i -ge 60) {
    docker compose logs cloud-server
    throw "cloud-server did not become healthy"
}

Write-Host "Authenticating CDK CLI..."
$Token | docker compose run --rm -T cdk login
if ($LASTEXITCODE -ne 0) {
    throw "cdk login failed"
}

Write-Host "Deploying benign function..."
$deployOutput = docker compose run --rm -T cdk deploy /workspace/examples/benign/handler.py
$deployOutput | ForEach-Object { Write-Host $_ }
if ($LASTEXITCODE -ne 0) {
    throw "benign deploy failed"
}

$deployText = $deployOutput -join "`n"
if ($deployText -notmatch "/run/([0-9a-fA-F-]+)") {
    throw "could not parse function id from deploy output"
}
$functionId = $Matches[1]

Write-Host "Listing functions..."
docker compose run --rm -T cdk list
if ($LASTEXITCODE -ne 0) {
    throw "cdk list failed"
}

Write-Host "Checking malicious function rejection..."
docker compose run --rm -T cdk deploy /workspace/examples/malicious/handler.py
if ($LASTEXITCODE -eq 0) {
    throw "malicious deploy unexpectedly passed"
}

Write-Host "Verifying invoke endpoint placeholder..."
$invokeStatus = & curl.exe -sS -o NUL -w "%{http_code}" -X POST -H "Authorization: Bearer $Token" "http://localhost:8000/run/$functionId"
if ($invokeStatus -ne "501") {
    throw "expected invoke placeholder status 501, got $invokeStatus"
}

Write-Host "Deleting function through CDK..."
"y" | docker compose run --rm -T cdk delete $functionId
if ($LASTEXITCODE -ne 0) {
    throw "cdk delete failed"
}

Write-Host "End-to-end Docker workflow passed."
