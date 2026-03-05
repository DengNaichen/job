#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

if [[ -x "./.venv/bin/pytest" ]]; then
  PYTEST_CMD=("./.venv/bin/pytest")
else
  PYTEST_CMD=("./scripts/uv" "run" "pytest")
fi

run_suite() {
  echo
  echo "\$ ${PYTEST_CMD[*]} $*"
  "${PYTEST_CMD[@]}" "$@"
}

run_suite tests/unit/ingest/fetchers -q
run_suite tests/unit/ingest/mappers -q
run_suite tests/unit/sync -q
run_suite tests/unit/repositories/test_job_repository_dedup.py tests/unit/services/application/blob/test_blob_storage.py tests/unit/scripts/test_migrate_job_blobs_to_storage.py -q
