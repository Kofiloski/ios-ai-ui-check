#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SCHEMA_CHECK_PATH="$(mktemp "${TMPDIR:-/tmp}/ios-ai-ui-check-schema.XXXXXX")"
trap 'rm -f "${SCHEMA_CHECK_PATH}"' EXIT

python3 scripts/ai_ui_contract.py write-schema --output "${SCHEMA_CHECK_PATH}"
if ! cmp -s "${SCHEMA_CHECK_PATH}" schemas/scenario.schema.json; then
  echo "schemas/scenario.schema.json is out of sync with scripts/ai_ui_contract.py" >&2
  diff -u schemas/scenario.schema.json "${SCHEMA_CHECK_PATH}" || true
  exit 1
fi
python3 -m compileall scripts tests
python3 -m unittest discover -s tests
git diff --check

echo "ios-ai-ui-check maintenance checks passed."
