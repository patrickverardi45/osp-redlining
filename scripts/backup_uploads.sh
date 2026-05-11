#!/usr/bin/env bash
# Step 0B — backup UPLOADS_DIR only (tar.gz). No backend/frontend behavior changes.
#
# Resolves source in order:
#   1) OSP_UPLOAD_DIR (if set and directory exists)
#   2) /data/uploads (Render persistent disk layout)
#   3) <repo>/backend/uploads (local dev fallback)
#
# Default output:
#   BACKUP_OUTPUT_DIR if set; else /data/backups when source is under /data; else <repo>/backups
#
# Usage:
#   ./scripts/backup_uploads.sh
#   OSP_UPLOAD_DIR=/data/uploads ./scripts/backup_uploads.sh
#   BACKUP_OUTPUT_DIR=/tmp ./scripts/backup_uploads.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

resolve_source() {
  if [[ -n "${OSP_UPLOAD_DIR:-}" ]] && [[ -d "$OSP_UPLOAD_DIR" ]]; then
    printf '%s' "$OSP_UPLOAD_DIR"
    return 0
  fi
  if [[ -d /data/uploads ]]; then
    printf '%s' "/data/uploads"
    return 0
  fi
  local dev="${REPO_ROOT}/backend/uploads"
  if [[ -d "$dev" ]]; then
    printf '%s' "$dev"
    return 0
  fi
  return 1
}

if ! SOURCE="$(resolve_source)"; then
  echo "ERROR: backup source not found. Set OSP_UPLOAD_DIR to an existing directory, or create ${REPO_ROOT}/backend/uploads for local dev." >&2
  exit 1
fi

if [[ ! -r "$SOURCE" ]]; then
  echo "ERROR: not readable: $SOURCE" >&2
  exit 1
fi

TAR_PARENT="$(cd "${SOURCE}/.." && pwd)"
TAR_NAME="$(basename "$SOURCE")"

GIT_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo nogit)"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

if [[ -n "${BACKUP_OUTPUT_DIR:-}" ]]; then
  OUTDIR="$BACKUP_OUTPUT_DIR"
elif [[ "$SOURCE" == /data/* ]] && [[ -d /data ]]; then
  OUTDIR="/data/backups"
else
  OUTDIR="${REPO_ROOT}/backups"
fi

mkdir -p "$OUTDIR"
OUTFILE="${OUTDIR}/truline-uploads-${TS}-${GIT_SHA}.tar.gz"

echo "SOURCE=${SOURCE}"
echo "OUTFILE=${OUTFILE}"
echo "GIT_SHA=${GIT_SHA}"

tar -czf "$OUTFILE" -C "$TAR_PARENT" "$TAR_NAME"

if ! tar -tzf "$OUTFILE" >/dev/null 2>&1; then
  echo "ERROR: tar -tzf verification failed for ${OUTFILE}" >&2
  rm -f "$OUTFILE" 2>/dev/null || true
  exit 1
fi

ENTRIES="$(tar -tzf "$OUTFILE" | wc -l | tr -d ' ')"
if [[ -z "$ENTRIES" ]] || [[ "$ENTRIES" -eq 0 ]]; then
  echo "ERROR: archive contains zero entries" >&2
  rm -f "$OUTFILE" 2>/dev/null || true
  exit 1
fi

echo "OK verified archive entries=${ENTRIES}"
echo "${OUTFILE}"
