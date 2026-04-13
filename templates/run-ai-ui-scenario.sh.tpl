#!/usr/bin/env bash
__SCAFFOLD_HEADER_SHELL__
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_PATH="${AI_UI_PROJECT_PATH:-$ROOT_DIR/__PROJECT_PATH__}"
SCHEME="${AI_UI_SCHEME:-__SCHEME__}"
UI_TEST_TARGET="${AI_UI_UI_TEST_TARGET:-__UI_TEST_TARGET__}"
MODE="run"
if [[ $# -gt 0 ]]; then
  case "$1" in
    run|inspect)
      MODE="$1"
      shift
      ;;
  esac
fi
SCENARIO_PATH="${AI_UI_SCENARIO_PATH:-${1:-$ROOT_DIR/__SCENARIO_PATH__}}"
ARTIFACTS_DIR="${AI_UI_ARTIFACTS_DIR:-$ROOT_DIR/artifacts/ai-ui/manual-$(date +%Y%m%d-%H%M%S)}"
SIM_DEVICE_NAME="${AI_UI_SIMULATOR_NAME:-${SIM_DEVICE_NAME:-__SIMULATOR_NAME__}}"
SIM_DEVICE_RUNTIME="${AI_UI_SIMULATOR_RUNTIME:-${SIM_DEVICE_RUNTIME:-__SIMULATOR_RUNTIME__}}"
SIM_DEVICE_ID="${AI_UI_SIMULATOR_UDID:-${SIM_DEVICE_ID:-}}"
SIM_DEVICE_ARCH="${AI_UI_SIMULATOR_ARCH:-$(uname -m)}"
DERIVED_DATA_PATH="${AI_UI_DERIVED_DATA_PATH:-$ROOT_DIR/.derivedData/ai-ui}"

absolute_path() {
  python3 - "$1" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).expanduser().resolve(strict=False))
PY
}

select_base_xctestrun() {
  find "$DERIVED_DATA_PATH/Build/Products" \
    -name '*.xctestrun' \
    ! -name '*-runtime.xctestrun' \
    -print -quit 2>/dev/null || true
}

patch_xctestrun_testing_env() {
  local plist_path="$1"
  local ui_test_target="$2"

  XCTESTRUN_PATH="$plist_path" \
  UI_TEST_TARGET="$ui_test_target" \
  AI_UI_SCENARIO_PATH="${SCENARIO_PATH:-}" \
  AI_UI_ARTIFACTS_DIR="${ARTIFACTS_DIR:-}" \
  AI_UI_EXPECTED_SCREENSHOT_PATH="${AI_UI_EXPECTED_SCREENSHOT_PATH:-}" \
  AI_UI_BEFORE_PLANNING_UI_TREE_PATH="${BEFORE_PLANNING_UI_TREE_PATH:-}" \
  AI_UI_BEFORE_PLANNING_SCREENSHOT_PATH="${BEFORE_PLANNING_SCREENSHOT_PATH:-}" \
  AI_UI_CURRENT_UI_TREE_PATH="${BEFORE_PLANNING_UI_TREE_PATH:-}" \
  AI_UI_CURRENT_SCREENSHOT_PATH="${BEFORE_PLANNING_SCREENSHOT_PATH:-}" \
  AI_UI_INSPECT_LAUNCH_ARGUMENTS_JSON="${AI_UI_INSPECT_LAUNCH_ARGUMENTS_JSON:-}" \
  AI_UI_INSPECT_LAUNCH_ENVIRONMENT_JSON="${AI_UI_INSPECT_LAUNCH_ENVIRONMENT_JSON:-}" \
  AI_UI_INSPECT_WAIT_SECONDS="${AI_UI_INSPECT_WAIT_SECONDS:-}" \
  python3 - <<'PY'
import os
import plistlib
from pathlib import Path

plist_path = Path(os.environ["XCTESTRUN_PATH"])
target_name = os.environ["UI_TEST_TARGET"]

updates = {}
for key in (
    "AI_UI_SCENARIO_PATH",
    "AI_UI_ARTIFACTS_DIR",
    "AI_UI_EXPECTED_SCREENSHOT_PATH",
    "AI_UI_BEFORE_PLANNING_UI_TREE_PATH",
    "AI_UI_BEFORE_PLANNING_SCREENSHOT_PATH",
    "AI_UI_CURRENT_UI_TREE_PATH",
    "AI_UI_CURRENT_SCREENSHOT_PATH",
    "AI_UI_INSPECT_LAUNCH_ARGUMENTS_JSON",
    "AI_UI_INSPECT_LAUNCH_ENVIRONMENT_JSON",
    "AI_UI_INSPECT_WAIT_SECONDS",
):
    value = os.environ.get(key, "")
    if value:
        updates[key] = value

with plist_path.open("rb") as handle:
    payload = plistlib.load(handle)

patched = False
for configuration in payload.get("TestConfigurations", []):
    for target in configuration.get("TestTargets", []):
        if target.get("BlueprintName") != target_name and target.get("ProductModuleName") != target_name:
            continue
        testing_environment = target.setdefault("TestingEnvironmentVariables", {})
        testing_environment.update(updates)
        patched = True

if not patched:
    legacy_target = payload.setdefault(target_name, {})
    testing_environment = legacy_target.setdefault("TestingEnvironmentVariables", {})
    testing_environment.update(updates)

with plist_path.open("wb") as handle:
    plistlib.dump(payload, handle, fmt=plistlib.FMT_XML, sort_keys=False)
PY
}

ARTIFACTS_DIR="$(absolute_path "$ARTIFACTS_DIR")"
DERIVED_DATA_PATH="$(absolute_path "$DERIVED_DATA_PATH")"
if [[ "$MODE" == "run" ]]; then
  SCENARIO_PATH="$(absolute_path "$SCENARIO_PATH")"
fi
if [[ -n "${AI_UI_EXPECTED_SCREENSHOT_PATH:-}" ]]; then
  AI_UI_EXPECTED_SCREENSHOT_PATH="$(absolute_path "${AI_UI_EXPECTED_SCREENSHOT_PATH}")"
fi
if [[ "$MODE" == "inspect" ]]; then
  LOG_PATH="$ARTIFACTS_DIR/xcodebuild-ui-inspect.log"
  RESULT_BUNDLE_PATH="$ARTIFACTS_DIR/${UI_TEST_TARGET}-inspect.xcresult"
  SUMMARY_PATH="$ARTIFACTS_DIR/inspect-summary.md"
else
  LOG_PATH="$ARTIFACTS_DIR/xcodebuild-ui-test.log"
  RESULT_BUNDLE_PATH="$ARTIFACTS_DIR/${UI_TEST_TARGET}.xcresult"
  SUMMARY_PATH="$ARTIFACTS_DIR/summary.md"
fi
BUILD_LOG_PATH="$ARTIFACTS_DIR/xcodebuild-build-for-testing.log"
BEFORE_PLANNING_UI_TREE_PATH="${AI_UI_BEFORE_PLANNING_UI_TREE_PATH:-${AI_UI_CURRENT_UI_TREE_PATH:-$ARTIFACTS_DIR/before-planning-ui-tree.json}}"
BEFORE_PLANNING_SCREENSHOT_PATH="${AI_UI_BEFORE_PLANNING_SCREENSHOT_PATH:-${AI_UI_CURRENT_SCREENSHOT_PATH:-$ARTIFACTS_DIR/before-planning-screenshot.png}}"

mkdir -p "$ARTIFACTS_DIR"
rm -rf "$RESULT_BUNDLE_PATH"

append_planner_goal_to_summary() {
  if [[ -z "${AI_UI_PLANNER_GOAL:-}" || ! -f "$SUMMARY_PATH" ]]; then
    return 0
  fi

  SUMMARY_PATH="$SUMMARY_PATH" \
  AI_UI_PLANNER_GOAL="${AI_UI_PLANNER_GOAL}" \
  python3 - <<'PY'
import os
import re
from pathlib import Path

summary_path = Path(os.environ["SUMMARY_PATH"])
planner_goal = os.environ.get("AI_UI_PLANNER_GOAL", "")
summary_text = summary_path.read_text(encoding="utf-8")

if (
    "### Planner Goal" in summary_text
    or "## Planner Goal" in summary_text
    or "- Planner goal:" in summary_text
):
    raise SystemExit(0)

if summary_text and not summary_text.endswith("\n"):
    summary_text += "\n"
if summary_text:
    summary_text += "\n"

fence_length = 3
for match in re.finditer(r"`+", planner_goal):
    fence_length = max(fence_length, len(match.group(0)) + 1)
fence = "`" * fence_length

summary_text += "### Planner Goal\n\n"
summary_text += f"{fence}text\n"
summary_text += planner_goal
if not planner_goal.endswith("\n"):
    summary_text += "\n"
summary_text += f"{fence}\n"

summary_path.write_text(summary_text, encoding="utf-8")
PY
}

append_planner_note_to_summary() {
  if [[ -z "${AI_UI_PLANNER_NOTE_PATH:-}" || ! -f "$SUMMARY_PATH" || ! -f "${AI_UI_PLANNER_NOTE_PATH}" ]]; then
    return 0
  fi

  SUMMARY_PATH="$SUMMARY_PATH" \
  AI_UI_PLANNER_NOTE_PATH="${AI_UI_PLANNER_NOTE_PATH}" \
  python3 - <<'PY'
import os
from pathlib import Path

summary_path = Path(os.environ["SUMMARY_PATH"])
planner_note_path = Path(os.environ["AI_UI_PLANNER_NOTE_PATH"])
summary_text = summary_path.read_text(encoding="utf-8")
planner_note = planner_note_path.read_text(encoding="utf-8").strip()

if not planner_note:
    raise SystemExit(0)

if "### Planner Note" in summary_text or "## Planner Note" in summary_text or "- Planner note:" in summary_text:
    raise SystemExit(0)

if summary_text and not summary_text.endswith("\n"):
    summary_text += "\n"
if summary_text:
    summary_text += "\n"

summary_text += "### Planner Note\n\n"
summary_text += planner_note
if not planner_note.endswith("\n"):
    summary_text += "\n"

summary_path.write_text(summary_text, encoding="utf-8")
PY
}

SCENARIO_NAME="Inspect current UI"
if [[ "$MODE" == "run" ]]; then
  if [[ ! -f "$SCENARIO_PATH" ]]; then
    echo "Scenario file not found: $SCENARIO_PATH" >&2
    exit 1
  fi

  SCENARIO_NAME="$(python3 - "$SCENARIO_PATH" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    payload = json.load(handle)

print(payload.get("name", "Unnamed scenario"))
PY
)"
fi

if [[ -z "$SIM_DEVICE_ID" ]]; then
  SIM_DEVICE_ID="$(python3 - "${SIM_DEVICE_NAME}" "${SIM_DEVICE_RUNTIME}" <<'PY'
import json
import re
import subprocess
import sys

simulator_name, simulator_runtime = sys.argv[1:3]
payload = json.loads(
    subprocess.check_output(
        ["xcrun", "simctl", "list", "devices", "available", "-j"],
        text=True,
    )
)

def parse_version(runtime_id: str) -> tuple[int, ...]:
    match = re.search(r"iOS[- ](.+)$", runtime_id)
    if not match:
        return tuple()
    raw = match.group(1).replace("-", ".")
    return tuple(int(token) for token in raw.split(".") if token.isdigit())

target = simulator_runtime.strip().lower().replace("ios", "").strip()
target = target.replace(" ", "").replace(".", "-")

candidates = []
for runtime_id, devices in payload.get("devices", {}).items():
    if "iOS" not in runtime_id:
        continue
    if target and not runtime_id.lower().endswith(target):
        continue
    for device in devices:
        if not device.get("isAvailable", False):
            continue
        if device.get("name") != simulator_name:
            continue
        candidates.append((parse_version(runtime_id), device["udid"]))

if not candidates:
    raise SystemExit("")

candidates.sort(reverse=True)
print(candidates[0][1])
PY
)"
fi

if [[ -z "$SIM_DEVICE_ID" ]]; then
  echo "Could not resolve a simulator UDID for device name/runtime: $SIM_DEVICE_NAME / $SIM_DEVICE_RUNTIME" >&2
  exit 1
fi

mkdir -p "$DERIVED_DATA_PATH"
build_duration_seconds=0
test_duration_seconds=0

destination="platform=iOS Simulator,id=$SIM_DEVICE_ID"
if [[ "$SIM_DEVICE_ARCH" == "arm64" || "$SIM_DEVICE_ARCH" == "x86_64" ]]; then
  destination="${destination},arch=$SIM_DEVICE_ARCH"
fi
xctestrun_path="$(select_base_xctestrun)"

if [[ -z "$xctestrun_path" || "${AI_UI_FORCE_BUILD_FOR_TESTING:-0}" == "1" ]]; then
  build_start="$(date +%s)"
  xcodebuild build-for-testing \
    -project "$PROJECT_PATH" \
    -scheme "$SCHEME" \
    -destination "$destination" \
    -parallel-testing-enabled NO \
    -showBuildTimingSummary \
    -derivedDataPath "$DERIVED_DATA_PATH" | tee "$BUILD_LOG_PATH"
  build_end="$(date +%s)"
  build_duration_seconds="$((build_end - build_start))"

  xctestrun_path="$(select_base_xctestrun)"
fi

if [[ -z "$xctestrun_path" ]]; then
  echo "Could not locate an .xctestrun file in $DERIVED_DATA_PATH/Build/Products" >&2
  exit 1
fi

runtime_xctestrun_path="$(dirname "$xctestrun_path")/${UI_TEST_TARGET}-runtime.xctestrun"
rm -f "$runtime_xctestrun_path"
cp "$xctestrun_path" "$runtime_xctestrun_path"

if [[ "$MODE" == "inspect" ]]; then
  BEFORE_PLANNING_UI_TREE_PATH="$(absolute_path "$BEFORE_PLANNING_UI_TREE_PATH")"
  BEFORE_PLANNING_SCREENSHOT_PATH="$(absolute_path "$BEFORE_PLANNING_SCREENSHOT_PATH")"
fi

patch_xctestrun_testing_env "$runtime_xctestrun_path" "$UI_TEST_TARGET"

set +e
test_start="$(date +%s)"
test_selector="${UI_TEST_TARGET}/ScenarioRunnerUITests/testScenario"
if [[ "$MODE" == "inspect" ]]; then
  test_selector="${UI_TEST_TARGET}/ScenarioRunnerUITests/testInspectUI"
fi
xcodebuild test-without-building \
  -xctestrun "$runtime_xctestrun_path" \
  -destination "$destination" \
  -parallel-testing-enabled NO \
  -only-testing:"${test_selector}" \
  -resultBundlePath "$RESULT_BUNDLE_PATH" | tee "$LOG_PATH"
test_exit="$?"
test_end="$(date +%s)"
set -e
test_duration_seconds="$((test_end - test_start))"

status="passed"
if [[ "$test_exit" -ne 0 ]]; then
  status="failed"
fi

{
  echo "## iOS AI UI Check"
  echo
  echo "- Scenario: $SCENARIO_NAME"
  echo "- Result: $status"
  echo "- Simulator: $SIM_DEVICE_NAME / iOS $SIM_DEVICE_RUNTIME ($SIM_DEVICE_ID)"
  echo "- Log: $(basename "$LOG_PATH")"
  if [[ -f "$BUILD_LOG_PATH" ]]; then
    echo "- Build log: $(basename "$BUILD_LOG_PATH")"
  fi
  echo "- Result bundle: $(basename "$RESULT_BUNDLE_PATH")"
  echo "- Build-for-testing duration: ${build_duration_seconds}s"
  echo "- UI test command duration: ${test_duration_seconds}s"
  if [[ "$MODE" == "inspect" ]]; then
    if [[ -f "${BEFORE_PLANNING_UI_TREE_PATH}" ]]; then
      echo "- Before-planning UI tree: ${BEFORE_PLANNING_UI_TREE_PATH}"
    else
      echo "- Before-planning UI tree: missing"
    fi
    if [[ -f "${BEFORE_PLANNING_SCREENSHOT_PATH}" ]]; then
      echo "- Before-planning screenshot: ${BEFORE_PLANNING_SCREENSHOT_PATH}"
    else
      echo "- Before-planning screenshot: missing"
    fi
  fi
  if [[ -n "${AI_UI_EXPECTED_SCREENSHOT_PATH:-}" ]]; then
    echo "- Expected screenshot: ${AI_UI_EXPECTED_SCREENSHOT_PATH}"
  fi
} > "$SUMMARY_PATH"

append_planner_goal_to_summary
append_planner_note_to_summary

if [[ "$MODE" == "inspect" ]]; then
  if [[ ! -f "${BEFORE_PLANNING_UI_TREE_PATH}" ]]; then
    echo "Inspect mode did not produce a UI tree at ${BEFORE_PLANNING_UI_TREE_PATH}" >&2
    exit 1
  fi
  if [[ ! -f "${BEFORE_PLANNING_SCREENSHOT_PATH}" ]]; then
    echo "Inspect mode did not produce a screenshot at ${BEFORE_PLANNING_SCREENSHOT_PATH}" >&2
    exit 1
  fi
fi

if [[ "$test_exit" -ne 0 ]]; then
  exit "$test_exit"
fi
