#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QA_RESULTS_FILE="${PROJECT_ROOT}/context/qa-results.md"
TEMP_DIRECTORY="$(mktemp -d)"
COVERAGE_LOG="${TEMP_DIRECTORY}/coverage.log"
SONAR_LOG="${TEMP_DIRECTORY}/sonar.log"

cleanup() {
  rm -rf "${TEMP_DIRECTORY}"
}

trap cleanup EXIT

mkdir -p "$(dirname "${QA_RESULTS_FILE}")"
cd "${PROJECT_ROOT}"

run_step() {
  local label="$1"
  local command_path="$2"
  local log_path="$3"

  echo "${label}"

  if [[ ! -x "${command_path}" ]]; then
    echo "ERROR: ${command_path} no existe o no es ejecutable" \
      | tee "${log_path}"
    return 1
  fi

  set +e
  "${command_path}" 2>&1 | tee "${log_path}"
  local status="${PIPESTATUS[0]}"
  set -e

  return "${status}"
}

COVERAGE_STATUS=0
SONAR_STATUS=0

run_step \
  "1/2 Ejecutando tests y coverage..." \
  "${PROJECT_ROOT}/scripts/coverage.sh" \
  "${COVERAGE_LOG}" \
  || COVERAGE_STATUS=$?

if [[ "${COVERAGE_STATUS}" -eq 0 ]]; then
  run_step \
    "2/2 Ejecutando SonarScanner..." \
    "${PROJECT_ROOT}/scripts/sonar-scan.sh" \
    "${SONAR_LOG}" \
    || SONAR_STATUS=$?
else
  SONAR_STATUS=1
  printf '%s\n' \
    "SonarScanner no se ejecutó porque tests o coverage fallaron." \
    > "${SONAR_LOG}"
fi

OVERALL_STATUS="passed"

if [[ "${COVERAGE_STATUS}" -ne 0 || "${SONAR_STATUS}" -ne 0 ]]; then
  OVERALL_STATUS="failed"
fi

{
  echo "# QA Results"
  echo
  echo "> **Generated at:** $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo ">"
  echo "> **Project:** SBM-AI-ASSISTANT"
  echo ">"
  echo "> **Overall status:** ${OVERALL_STATUS}"
  echo
  echo "## Tests and coverage"
  echo
  echo "- Exit code: ${COVERAGE_STATUS}"
  echo
  echo '```text'
  cat "${COVERAGE_LOG}"
  echo '```'
  echo
  echo "## SonarScanner"
  echo
  echo "- Exit code: ${SONAR_STATUS}"
  echo
  echo '```text'
  cat "${SONAR_LOG}"
  echo '```'
  echo
  echo "## Evidence boundary"
  echo
  echo "This file records only the output produced by the executed QA scripts."
  echo "It does not infer coverage, SonarQube status, deployments or quality gates not present in the logs."
} > "${QA_RESULTS_FILE}"

echo
echo "Evidencia QA generada en: ${QA_RESULTS_FILE}"

if [[ "${COVERAGE_STATUS}" -ne 0 ]]; then
  echo "ERROR: Tests o coverage fallaron."
  exit "${COVERAGE_STATUS}"
fi

if [[ "${SONAR_STATUS}" -ne 0 ]]; then
  echo "ERROR: SonarScanner falló."
  exit "${SONAR_STATUS}"
fi

echo "QA completado correctamente."
