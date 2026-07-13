#!/usr/bin/env bash
set -euo pipefail

INCLUDE_DIR="/Users/neto_alvarez/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Include/v30"
EXPERT_DIR="/Users/neto_alvarez/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Experts/Advisors"
OUT_DIR="${HOME}/Desktop/stage10d_phase1_sources"
ZIP_PATH="${HOME}/Desktop/stage10d_phase1_sources.zip"

rm -rf "${OUT_DIR}"
mkdir -p "${OUT_DIR}/Include/v30" "${OUT_DIR}/Experts/Advisors"

copy_required() {
  local source_dir="$1"
  local filename="$2"
  local destination_dir="$3"
  local source_path

  source_path="$(find "${source_dir}" -type f -name "${filename}" -print -quit)"
  if [[ -z "${source_path}" ]]; then
    echo "ERROR: no se encontró ${filename} dentro de ${source_dir}" >&2
    exit 1
  fi

  cp -p "${source_path}" "${destination_dir}/"
  echo "COPIED: ${source_path}"
}

copy_required "${INCLUDE_DIR}" "H4Signal.mqh" "${OUT_DIR}/Include/v30"
copy_required "${INCLUDE_DIR}" "D1Context.mqh" "${OUT_DIR}/Include/v30"

EXPERT_PATH="$(find "${EXPERT_DIR}" -maxdepth 2 -type f \( \
  -iname '*v4430*.mq5' -o \
  -iname '*v4.43.0*.mq5' -o \
  -iname '*stage10c*.mq5' \
\) -print | head -n 1)"

if [[ -z "${EXPERT_PATH}" ]]; then
  echo "ERROR: no se encontró el experto v4.43.0/Stage10C en ${EXPERT_DIR}" >&2
  exit 1
fi

cp -p "${EXPERT_PATH}" "${OUT_DIR}/Experts/Advisors/"
echo "COPIED: ${EXPERT_PATH}"

{
  echo "generated_at_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "include_dir=${INCLUDE_DIR}"
  echo "expert_dir=${EXPERT_DIR}"
  echo "files:"
  find "${OUT_DIR}" -type f ! -name MANIFEST.txt -print | sort
  echo "sha256:"
  find "${OUT_DIR}" -type f ! -name MANIFEST.txt -print0 | sort -z | xargs -0 shasum -a 256
} > "${OUT_DIR}/MANIFEST.txt"

rm -f "${ZIP_PATH}"
(
  cd "$(dirname "${OUT_DIR}")"
  zip -rq "${ZIP_PATH}" "$(basename "${OUT_DIR}")"
)

echo
printf 'OK: paquete creado en:\n%s\n' "${ZIP_PATH}"
echo "Sube ese ZIP a esta conversación para completar la Fase 1."
