#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${PROJECT_ROOT}"

echo "QA sbm-ai-assistant aislado"
docker compose run --rm --no-deps backend pytest -q
echo "QA sbm-ai-assistant completado correctamente."
