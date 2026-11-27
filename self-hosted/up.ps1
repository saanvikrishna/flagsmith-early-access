$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $RepoRoot
try {
    docker compose up -d postgres flagsmith
    python self-hosted/bootstrap.py --url http://localhost:8000 --env-file .env
    docker compose up -d --build demo-app

    Write-Host "Flagsmith UI: http://localhost:8000"
    Write-Host "Demo App:     http://localhost:3000"
}
finally {
    Pop-Location
}
