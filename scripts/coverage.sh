#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${PROJECT_ROOT}"
rm -f coverage.xml

docker compose run \
  --rm \
  --no-deps \
  -v "${PROJECT_ROOT}:/workspace" \
  -w /workspace \
  -e PYTHONPATH=/workspace/backend \
  backend \
  pytest -q backend/tests \
    --cov=backend/app \
    --cov-branch \
    --cov-config=.coveragerc \
    --cov-report=term-missing \
    --cov-report=xml:/workspace/coverage.xml

[[ -f coverage.xml ]] || {
  echo "ERROR: No se generó coverage.xml"
  exit 1
}

echo "Coverage generado correctamente."
