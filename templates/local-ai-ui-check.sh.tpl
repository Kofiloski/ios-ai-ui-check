#!/usr/bin/env bash
__SCAFFOLD_HEADER_SHELL__
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_SCENARIO_PATH="$ROOT_DIR/__SCENARIO_PATH__"
SIM_DEVICE_NAME="${SIM_DEVICE_NAME:-__SIMULATOR_NAME__}"
SIM_DEVICE_RUNTIME="${SIM_DEVICE_RUNTIME:-__SIMULATOR_RUNTIME__}"
SIM_DEVICE_ID="${SIM_DEVICE_ID:-}"
ARTIFACTS_DIR="${ARTIFACTS_DIR:-$ROOT_DIR/artifacts/ai-ui/local-$(date +%Y%m%d-%H%M%S)}"
DERIVED_DATA_PATH="${AI_UI_DERIVED_DATA_PATH:-$ROOT_DIR/.derivedData/ai-ui}"
PLANNER_GOAL="${AI_UI_PLANNER_GOAL:-${PLANNER_GOAL:-}}"
PLANNER_MODEL="${AI_UI_PLANNER_MODEL:-${PLANNER_MODEL:-}}"
SCENARIO_PATH=""
MODE=""
USE_EXAMPLE_SCENARIO=0

usage() {
  cat <<EOF
Usage:
  $(basename "$0") [--scenario PATH]
  $(basename "$0") --use-example-scenario
  $(basename "$0") [--goal "test adding an ingredient"]

Options:
  --scenario PATH           Run the specified scenario JSON file.
  --use-example-scenario    Run the checked-in scenario example.
  --goal TEXT               Ask the planner to verify a short human goal.
  --planner-model MODEL     Planner model passed through as AI_UI_PLANNER_MODEL.
  --artifacts-dir DIR       Directory for logs, screenshots, and xcresult output.
  --derived-data-path DIR   DerivedData path for build-for-testing output.
  --simulator-name NAME     Simulator device name. Default: __SIMULATOR_NAME__
  --simulator-runtime VER   Simulator runtime version. Default: __SIMULATOR_RUNTIME__
  --simulator-id UDID       Explicit simulator UDID.
  -h, --help                Show this help text.

Examples:
  $(basename "$0") --goal "test adding an ingredient"
  $(basename "$0") --use-example-scenario
  $(basename "$0") --scenario __SCENARIO_PATH__

Notes:
  - AI planning requires OPENAI_API_KEY and scripts/plan-ai-ui-scenario.sh.
  - The helper does not silently fall back from AI planning to the example scenario.
    If you want the checked-in example, pass --use-example-scenario explicitly.
EOF
}

die() {
  echo "$*" >&2
  exit 1
}

absolute_path() {
  python3 - "$1" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).expanduser().resolve(strict=False))
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scenario)
      [[ $# -ge 2 ]] || die "--scenario requires a path"
      SCENARIO_PATH="$2"
      shift 2
      ;;
    --use-example-scenario)
      USE_EXAMPLE_SCENARIO=1
      shift
      ;;
    --goal)
      [[ $# -ge 2 ]] || die "--goal requires text"
      PLANNER_GOAL="$2"
      shift 2
      ;;
    --planner-model)
      [[ $# -ge 2 ]] || die "--planner-model requires a value"
      PLANNER_MODEL="$2"
      shift 2
      ;;
    --artifacts-dir)
      [[ $# -ge 2 ]] || die "--artifacts-dir requires a path"
      ARTIFACTS_DIR="$2"
      shift 2
      ;;
    --derived-data-path)
      [[ $# -ge 2 ]] || die "--derived-data-path requires a path"
      DERIVED_DATA_PATH="$2"
      shift 2
      ;;
    --simulator-name)
      [[ $# -ge 2 ]] || die "--simulator-name requires a value"
      SIM_DEVICE_NAME="$2"
      shift 2
      ;;
    --simulator-runtime)
      [[ $# -ge 2 ]] || die "--simulator-runtime requires a value"
      SIM_DEVICE_RUNTIME="$2"
      shift 2
      ;;
    --simulator-id)
      [[ $# -ge 2 ]] || die "--simulator-id requires a value"
      SIM_DEVICE_ID="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      die "Unknown option: $1"
      ;;
    *)
      if [[ -z "$SCENARIO_PATH" ]]; then
        SCENARIO_PATH="$1"
        shift
      else
        die "Unexpected extra argument: $1"
      fi
      ;;
  esac
done

if [[ $# -gt 0 ]]; then
  die "Unexpected extra arguments: $*"
fi

if [[ -n "$SCENARIO_PATH" && "$USE_EXAMPLE_SCENARIO" == "1" ]]; then
  die "Choose either --scenario or --use-example-scenario, not both"
fi

ARTIFACTS_DIR="$(absolute_path "$ARTIFACTS_DIR")"
DERIVED_DATA_PATH="$(absolute_path "$DERIVED_DATA_PATH")"
if [[ -n "$SCENARIO_PATH" ]]; then
  SCENARIO_PATH="$(absolute_path "$SCENARIO_PATH")"
fi

if [[ -n "$SCENARIO_PATH" ]]; then
  MODE="provided-scenario"
elif [[ "$USE_EXAMPLE_SCENARIO" == "1" ]]; then
  MODE="example-scenario"
  SCENARIO_PATH="$(absolute_path "$DEFAULT_SCENARIO_PATH")"
else
  MODE="ai-planned"
  SCENARIO_PATH="$ARTIFACTS_DIR/scenario.json"
fi

if [[ "$MODE" != "ai-planned" ]]; then
  [[ -f "$SCENARIO_PATH" ]] || die "Scenario file not found: $SCENARIO_PATH"
fi

if [[ "$MODE" == "ai-planned" ]]; then
  [[ -n "${OPENAI_API_KEY:-}" ]] || die "AI planning requires OPENAI_API_KEY. Pass --use-example-scenario or --scenario if you want a deterministic run."
  [[ -x "$ROOT_DIR/scripts/plan-ai-ui-scenario.sh" ]] || die "Planner script not found or not executable: $ROOT_DIR/scripts/plan-ai-ui-scenario.sh"
fi

mkdir -p "$ARTIFACTS_DIR"
export AI_UI_ARTIFACTS_DIR="$ARTIFACTS_DIR"
export AI_UI_SIMULATOR_NAME="$SIM_DEVICE_NAME"
export AI_UI_SIMULATOR_RUNTIME="$SIM_DEVICE_RUNTIME"
export AI_UI_DERIVED_DATA_PATH="$DERIVED_DATA_PATH"

if [[ -n "$SIM_DEVICE_ID" ]]; then
  export AI_UI_SIMULATOR_UDID="$SIM_DEVICE_ID"
fi

if [[ -n "$PLANNER_MODEL" ]]; then
  export AI_UI_PLANNER_MODEL="$PLANNER_MODEL"
fi

if [[ "$MODE" == "ai-planned" ]]; then
  SCENARIO_PATH="$ARTIFACTS_DIR/scenario.json"
  export AI_UI_BEFORE_PLANNING_UI_TREE_PATH="$ARTIFACTS_DIR/before-planning-ui-tree.json"
  export AI_UI_BEFORE_PLANNING_SCREENSHOT_PATH="$ARTIFACTS_DIR/before-planning-screenshot.png"
  export AI_UI_CURRENT_UI_TREE_PATH="$AI_UI_BEFORE_PLANNING_UI_TREE_PATH"
  export AI_UI_CURRENT_SCREENSHOT_PATH="$AI_UI_BEFORE_PLANNING_SCREENSHOT_PATH"
  export AI_UI_PLANNER_NOTE_OUTPUT_PATH="$ARTIFACTS_DIR/planner-note.md"
  export AI_UI_PLANNER_NOTE_PATH="$ARTIFACTS_DIR/planner-note.md"
  export AI_UI_PLANNER_GOAL="$PLANNER_GOAL"

  {
    echo "Local AI UI Check"
    echo "- Mode: $MODE"
    echo "- Goal: ${PLANNER_GOAL:-none}"
    echo "- Planner model: ${AI_UI_PLANNER_MODEL:-default}"
    echo "- Simulator: $SIM_DEVICE_NAME / iOS $SIM_DEVICE_RUNTIME"
    echo "- Artifacts: $ARTIFACTS_DIR"
  }

  "$ROOT_DIR/scripts/run-ai-ui-scenario.sh" inspect || true
  export AI_UI_SCENARIO_OUTPUT_PATH="$SCENARIO_PATH"
  export AI_UI_PLANNER_DRAFT_SCENARIO_PATH="$ARTIFACTS_DIR/planner-response.json"
  export AI_UI_WORKSPACE="$ROOT_DIR"
  "$ROOT_DIR/scripts/plan-ai-ui-scenario.sh"
else
  unset AI_UI_BEFORE_PLANNING_UI_TREE_PATH 2>/dev/null || true
  unset AI_UI_BEFORE_PLANNING_SCREENSHOT_PATH 2>/dev/null || true
  unset AI_UI_CURRENT_UI_TREE_PATH 2>/dev/null || true
  unset AI_UI_CURRENT_SCREENSHOT_PATH 2>/dev/null || true
  unset AI_UI_PLANNER_GOAL 2>/dev/null || true
  unset AI_UI_PLANNER_NOTE_OUTPUT_PATH 2>/dev/null || true
  unset AI_UI_PLANNER_NOTE_PATH 2>/dev/null || true
  unset AI_UI_PLANNER_DRAFT_SCENARIO_PATH 2>/dev/null || true
  if [[ -n "${PLANNER_GOAL:-}" ]]; then
    echo "Ignoring planner goal because this run is using a checked-in scenario." >&2
  fi
fi

export AI_UI_SCENARIO_PATH="$SCENARIO_PATH"

{
  echo "Local AI UI Check"
  echo "- Mode: $MODE"
  echo "- Scenario: $SCENARIO_PATH"
  echo "- Simulator: $SIM_DEVICE_NAME / iOS $SIM_DEVICE_RUNTIME"
  echo "- Artifacts: $ARTIFACTS_DIR"
}

"$ROOT_DIR/scripts/run-ai-ui-scenario.sh"

echo "AI UI artifacts ready in: $ARTIFACTS_DIR"
