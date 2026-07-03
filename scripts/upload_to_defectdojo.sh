#!/usr/bin/env bash
# upload_to_defectdojo.sh — reimport a scan report into DefectDojo
#
# Usage:
#   upload_to_defectdojo.sh <scan_type_or_test_title> <report_file> [api_scan_type]
#
#   $1  SCAN_TYPE   — test_title sent to DefectDojo (e.g. "Trivy Scan FS", "Gitleaks Scan")
#   $2  FILE        — path to the report file to upload
#   $3  SCAN_TYPE_API (optional) — the DefectDojo-registered scan_type when it differs from $1
#                   Example: ./upload_to_defectdojo.sh "Trivy Scan FS" file.json "Trivy Scan"
#                   If omitted, scan_type defaults to $1.
#
# Required environment variables:
#   DEFECTDOJO_URL        Base URL of the DefectDojo instance (no trailing slash)
#   DEFECTDOJO_TOKEN      API token (Authorization header)
#   DEFECTDOJO_PRODUCT_ID Numeric product ID
#
# Optional environment variables:
#   DEFECTDOJO_PRODUCT_NAME  Product name (default "FinSight"). Required by
#                            DefectDojo whenever auto_create_context=true.
#
# Optional environment variables (all default to "local" when unset):
#   GITHUB_SHA            Commit hash
#   GITHUB_RUN_ID         CI run ID
#   GITHUB_REF_NAME       Branch/tag name

set -euo pipefail

SCAN_TYPE="${1:?Usage: $0 <scan_type> <file> [api_scan_type]}"
FILE="${2:?Usage: $0 <scan_type> <file> [api_scan_type]}"
SCAN_TYPE_API="${3:-${SCAN_TYPE}}"

# ---------------------------------------------------------------------------
# Guard 1 — required environment variables (configuration errors, not skips)
# ---------------------------------------------------------------------------
if [ -z "${DEFECTDOJO_URL:-}" ]; then
  echo "ERROR: DEFECTDOJO_URL is not set or empty. Cannot upload to DefectDojo." >&2
  exit 1
fi

if [ -z "${DEFECTDOJO_TOKEN:-}" ]; then
  echo "ERROR: DEFECTDOJO_TOKEN is not set or empty. Cannot upload to DefectDojo." >&2
  exit 1
fi

if [ -z "${DEFECTDOJO_PRODUCT_ID:-}" ]; then
  echo "ERROR: DEFECTDOJO_PRODUCT_ID is not set or empty. Cannot upload to DefectDojo." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Guard 2 — missing report file (skip cleanly, do not red CI)
# ---------------------------------------------------------------------------
if [ ! -f "${FILE}" ]; then
  echo "INFO: Report file '${FILE}' not found. Skipping upload for '${SCAN_TYPE}'." >&2
  exit 0
fi

# ---------------------------------------------------------------------------
# TruffleHog NDJSON pre-processing
# TruffleHog emits one JSON object per line; DefectDojo expects only the lines
# that contain "SourceMetadata". Strip carriage returns so the temp file is
# clean. Trap ensures cleanup on any exit path.
# ---------------------------------------------------------------------------
TMP=""
if [ "${SCAN_TYPE}" = "Trufflehog Scan" ]; then
  TMP="$(mktemp)"
  trap 'rm -f "${TMP}"' EXIT
  grep '"SourceMetadata"' "${FILE}" | tr -d '\r' > "${TMP}"
  FILE="${TMP}"
fi

# ---------------------------------------------------------------------------
# Build CI metadata fields (default to "local" when not in GitHub Actions)
# ---------------------------------------------------------------------------
VERSION="${GITHUB_SHA:-local}"
BUILD_ID="${GITHUB_RUN_ID:-local}"
COMMIT_HASH="${GITHUB_SHA:-local}"
BRANCH_TAG="${GITHUB_REF_NAME:-local}"

# ---------------------------------------------------------------------------
# POST to DefectDojo reimport-scan endpoint
# -sS   : silent but show errors
# -w    : capture HTTP status for manual checking (-f intentionally not used:
#         it would exit before we can read the status code)
# The Authorization header carries the token; it is NEVER echoed or logged.
# ---------------------------------------------------------------------------
echo "INFO: Uploading '${SCAN_TYPE}' (scan_type: '${SCAN_TYPE_API}') from '${FILE}' ..." >&2

HTTP_STATUS=$(
  curl -sS \
    -o /dev/null \
    -w '%{http_code}' \
    -H "Authorization: Token ${DEFECTDOJO_TOKEN}" \
    -F "product_id=${DEFECTDOJO_PRODUCT_ID}" \
    -F "product_name=${DEFECTDOJO_PRODUCT_NAME:-FinSight}" \
    -F "engagement_name=CI Security Scan" \
    -F "test_title=${SCAN_TYPE}" \
    -F "scan_type=${SCAN_TYPE_API}" \
    -F "file=@${FILE}" \
    -F "auto_create_context=true" \
    -F "close_old_findings=true" \
    -F "version=${VERSION}" \
    -F "build_id=${BUILD_ID}" \
    -F "commit_hash=${COMMIT_HASH}" \
    -F "branch_tag=${BRANCH_TAG}" \
    "${DEFECTDOJO_URL}/api/v2/reimport-scan/"
)

if [ "${HTTP_STATUS}" -lt 200 ] || [ "${HTTP_STATUS}" -ge 300 ]; then
  echo "ERROR: DefectDojo API returned HTTP ${HTTP_STATUS} for '${SCAN_TYPE}'." >&2
  exit 1
fi

echo "INFO: Upload successful for '${SCAN_TYPE}' (HTTP ${HTTP_STATUS})." >&2
exit 0
