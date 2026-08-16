#!/usr/bin/env bash
set -euo pipefail

ENV_FILE=".env.dev"
REPORT_FILE="report-task.txt"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: No existe ${ENV_FILE}"
  exit 1
fi

SONAR_HOST_URL="$(
  grep '^SONAR_HOST_URL=' "${ENV_FILE}" |
    head -n 1 |
    cut -d= -f2-
)"

SONAR_API_URL="$(
  grep '^SONAR_API_URL=' "${ENV_FILE}" |
    head -n 1 |
    cut -d= -f2-
)"

SONAR_TOKEN="$(
  grep '^SONAR_TOKEN=' "${ENV_FILE}" |
    head -n 1 |
    cut -d= -f2-
)"

if [[ -z "${SONAR_HOST_URL}" ]]; then
  echo "ERROR: SONAR_HOST_URL no está definido"
  exit 1
fi

if [[ -z "${SONAR_API_URL}" ]]; then
  echo "ERROR: SONAR_API_URL no está definido"
  exit 1
fi

if [[ -z "${SONAR_TOKEN}" ]]; then
  echo "ERROR: SONAR_TOKEN no está definido"
  exit 1
fi

rm -f "${REPORT_FILE}"

docker run --rm \
  --env-file "${ENV_FILE}" \
  -v "$(pwd):/usr/src/app" \
  -v "$(pwd)/.sonar/cache:/opt/sonar-scanner/.sonar/cache" \
  -w /usr/src/app \
  sonarsource/sonar-scanner-cli \
  -Dsonar.host.url="${SONAR_HOST_URL}" \
  -Dsonar.scanner.metadataFilePath=/usr/src/app/report-task.txt

if [[ ! -f "${REPORT_FILE}" ]]; then
  echo "ERROR: No se generó ${REPORT_FILE}"
  exit 1
fi

CE_TASK_URL="$(
  grep '^ceTaskUrl=' "${REPORT_FILE}" |
    cut -d= -f2-
)"

if [[ -z "${CE_TASK_URL}" ]]; then
  echo "ERROR: No se encontró ceTaskUrl en ${REPORT_FILE}"
  exit 1
fi

CE_TASK_PATH="${CE_TASK_URL#*://}"
CE_TASK_PATH="/${CE_TASK_PATH#*/}"

echo "Esperando procesamiento de SonarQube..."

while true; do
  CE_RESPONSE="$(
    curl --silent --show-error --fail \
      --header "Authorization: Bearer ${SONAR_TOKEN}" \
      "${SONAR_API_URL}${CE_TASK_PATH}"
  )"

  CE_STATUS="$(
    printf '%s' "${CE_RESPONSE}" |
      python3 -c 'import json,sys; print(json.load(sys.stdin)["task"]["status"])'
  )"

  case "${CE_STATUS}" in
    SUCCESS)
      break
      ;;
    FAILED|CANCELED)
      echo "ERROR: SonarQube Compute Engine terminó en ${CE_STATUS}"
      exit 1
      ;;
    PENDING|IN_PROGRESS)
      sleep 2
      ;;
    *)
      echo "ERROR: Estado desconocido de Compute Engine: ${CE_STATUS}"
      exit 1
      ;;
  esac
done

ANALYSIS_ID="$(
  printf '%s' "${CE_RESPONSE}" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["task"]["analysisId"])'
)"

if [[ -z "${ANALYSIS_ID}" ]]; then
  echo "ERROR: No se obtuvo analysisId"
  exit 1
fi

QUALITY_RESPONSE="$(
  curl --silent --show-error --fail \
    --header "Authorization: Bearer ${SONAR_TOKEN}" \
    "${SONAR_API_URL}/api/qualitygates/project_status?analysisId=${ANALYSIS_ID}"
)"

QUALITY_STATUS="$(
  printf '%s' "${QUALITY_RESPONSE}" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["projectStatus"]["status"])'
)"

echo "Quality Gate: ${QUALITY_STATUS}"

case "${QUALITY_STATUS}" in
  OK)
    echo "SonarQube Quality Gate aprobado."
    ;;
  WARN)
    echo "WARNING: SonarQube Quality Gate con advertencias."
    ;;
  ERROR)
    echo "ERROR: SonarQube Quality Gate falló."
    exit 1
    ;;
  NONE)
    echo "ERROR: SonarQube no devolvió un Quality Gate."
    exit 1
    ;;
  *)
    echo "ERROR: Estado desconocido de Quality Gate: ${QUALITY_STATUS}"
    exit 1
    ;;
esac
