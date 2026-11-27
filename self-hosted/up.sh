#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

docker compose up -d postgres flagsmith
python3 self-hosted/bootstrap.py --url http://localhost:8000 --env-file .env
docker compose up -d --build demo-app

echo "Flagsmith UI: http://localhost:8000"
echo "Demo App:     http://localhost:3000"
