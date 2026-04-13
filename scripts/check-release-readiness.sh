#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

./scripts/check-maintenance.sh

EXPECTED_EXECUTABLES=(
  "scripts/ai_ui_contract.py"
  "scripts/boot-simulator.sh"
  "scripts/check-maintenance.sh"
  "scripts/check-release-readiness.sh"
  "scripts/plan-scenario.sh"
  "scripts/post-pr-comment.sh"
  "scripts/record-video.sh"
  "scripts/refresh-scaffold.py"
  "scripts/run-check.sh"
  "scripts/scaffold-app-repo.py"
  "scripts/write-artifact-manifest.py"
)

missing_exec=0
for path in "${EXPECTED_EXECUTABLES[@]}"; do
  if [[ ! -x "$path" ]]; then
    echo "Missing executable bit: $path" >&2
    missing_exec=1
  fi
done

if [[ "$missing_exec" -ne 0 ]]; then
  exit 1
fi

echo "Changed release surfaces:"
git status --short -- .github/workflows docs schemas templates README.md

echo "Release readiness checks passed."
