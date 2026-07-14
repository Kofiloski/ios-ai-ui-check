#!/usr/bin/env bash

set -euo pipefail

if [[ "$#" -gt 1 ]]; then
  echo "Usage: $0 [vMAJOR.MINOR.PATCH]" >&2
  exit 2
fi

VERSION_TAG="${1:-}"

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
  "scripts/run-with-timeout.py"
  "scripts/run-check.sh"
  "scripts/scaffold-app-repo.py"
  "scripts/write-artifact-manifest.py"
  "scripts/write-job-summary.py"
)

missing_exec=0
for path in "${EXPECTED_EXECUTABLES[@]}"; do
  if [[ ! -x "$path" ]]; then
    echo "Missing executable bit: $path" >&2
    missing_exec=1
  fi
done

if [[ -n "${VERSION_TAG}" ]]; then
  python3 - "${VERSION_TAG}" <<'PY'
import re
import sys
from pathlib import Path

version_tag = sys.argv[1]
if re.fullmatch(r"v\d+\.\d+\.\d+", version_tag) is None:
    raise SystemExit("release tag must match vMAJOR.MINOR.PATCH")

citation = Path("CITATION.cff").read_text(encoding="utf-8")
match = re.search(r"^version:\s*[\"']?([^\"'\s]+)", citation, re.MULTILINE)
if match is None:
    raise SystemExit("CITATION.cff is missing a version")

expected = f"v{match.group(1)}"
if version_tag != expected:
    raise SystemExit(
        f"requested release {version_tag} does not match CITATION.cff {expected}"
    )

for relative_path in (
    "README.md",
    "llms.txt",
    "examples/README.md",
    "examples/deterministic-pr-check.yml",
):
    if version_tag not in Path(relative_path).read_text(encoding="utf-8"):
        raise SystemExit(f"{relative_path} does not advertise {version_tag}")
PY
fi

if [[ "$missing_exec" -ne 0 ]]; then
  exit 1
fi

EXPECTED_PUBLIC_METADATA=(
  "README.md"
  "LICENSE"
  "action.yml"
  "CITATION.cff"
  "llms.txt"
  "examples/deterministic-pr-check.yml"
)

for path in "${EXPECTED_PUBLIC_METADATA[@]}"; do
  if [[ ! -s "$path" ]]; then
    echo "Missing or empty public metadata file: $path" >&2
    exit 1
  fi
done

echo "Changed release surfaces:"
git status --short -- .github/workflows docs examples schemas templates CITATION.cff LICENSE README.md action.yml llms.txt

echo "Release readiness checks passed."
