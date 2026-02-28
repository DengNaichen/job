#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  source "${ROOT_DIR}/.env"
  set +a
fi

if [[ ! -f "${ROOT_DIR}/.env.supabase.local" ]]; then
  echo "Missing ${ROOT_DIR}/.env.supabase.local" >&2
  exit 1
fi

set -a
source "${ROOT_DIR}/.env.supabase.local"
set +a

exec "$@"
