#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 scripts/ai_ui_contract.py write-schema --output schemas/scenario.schema.json
python3 -m compileall scripts tests
python3 -m unittest discover -s tests
git diff --check

echo "ios-ai-ui-check maintenance checks passed."
