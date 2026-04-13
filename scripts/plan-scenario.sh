#!/usr/bin/env bash

set -euo pipefail

ARTIFACTS_DIR="${ARTIFACTS_DIR:?ARTIFACTS_DIR is required}"
PROVIDED_SCENARIO_PATH="${PROVIDED_SCENARIO_PATH:-}"
PLANNER_COMMAND="${PLANNER_COMMAND:-}"
PLANNER_GOAL="${PLANNER_GOAL:-}"
ACTION_ROOT="${ACTION_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RUNNER_SCRIPT="${RUNNER_SCRIPT:-./scripts/run-ai-ui-scenario.sh}"
SIMULATOR_NAME="${SIMULATOR_NAME:-}"
SIMULATOR_RUNTIME="${SIMULATOR_RUNTIME:-26.2}"
MAX_DURATION_SECONDS="${MAX_DURATION_SECONDS:-300}"
AI_UI_CONTRACT_SCRIPT="${ACTION_ROOT}/scripts/ai_ui_contract.py"

absolute_path() {
  python3 - "$1" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).expanduser().resolve(strict=False))
PY
}

ARTIFACTS_DIR="$(absolute_path "${ARTIFACTS_DIR}")"
SCENARIO_PATH="${ARTIFACTS_DIR}/scenario.json"
SUMMARY_PATH="${ARTIFACTS_DIR}/summary.md"
PLANNER_SUMMARY_PATH="${ARTIFACTS_DIR}/planner-summary.md"
PLANNER_REQUEST_PATH="${ARTIFACTS_DIR}/planner-request.md"
PLANNER_RESPONSE_TEXT_PATH="${ARTIFACTS_DIR}/planner-response.txt"
PLANNER_RESPONSE_JSON_PATH="${ARTIFACTS_DIR}/planner-response.json"
PLANNER_VALIDATION_ERROR_PATH="${ARTIFACTS_DIR}/planner-validation-error.txt"
PLANNER_NOTE_PATH="${ARTIFACTS_DIR}/planner-note.md"
WORKSPACE_ROOT="$(absolute_path "${AI_UI_WORKSPACE:-${GITHUB_WORKSPACE:-$PWD}}")"
AI_UI_CONFIG_DIR="${WORKSPACE_ROOT}/.github/ai-ui"
PLANNER_CONTEXT_PATH="${AI_UI_PLANNER_CONTEXT_PATH:-${AI_UI_CONFIG_DIR}/planner-context.md}"
if [[ -n "${PROVIDED_SCENARIO_PATH}" ]]; then
  PROVIDED_SCENARIO_PATH="$(absolute_path "${PROVIDED_SCENARIO_PATH}")"
fi
if [[ -n "${EXPECTED_SCREENSHOT_PATH:-}" ]]; then
  EXPECTED_SCREENSHOT_PATH="$(absolute_path "${EXPECTED_SCREENSHOT_PATH}")"
fi

mkdir -p "${ARTIFACTS_DIR}"
rm -f \
  "${SCENARIO_PATH}" \
  "${SUMMARY_PATH}" \
  "${PLANNER_SUMMARY_PATH}" \
  "${PLANNER_REQUEST_PATH}" \
  "${PLANNER_RESPONSE_TEXT_PATH}" \
  "${PLANNER_RESPONSE_JSON_PATH}" \
  "${PLANNER_VALIDATION_ERROR_PATH}" \
  "${PLANNER_NOTE_PATH}"

STATUS="passed"
RESOLVED_SOURCE=""
ATTEMPTED_SOURCE=""
FAILURE_NOTE=""
BEFORE_PLANNING_UI_TREE_PATH=""
BEFORE_PLANNING_SCREENSHOT_PATH=""

trim_file_if_empty() {
  local path="$1"

  if [[ -f "${path}" && ! -s "${path}" ]]; then
    rm -f "${path}"
  fi
}

relative_artifact_path() {
  python3 - "${ARTIFACTS_DIR}" "$1" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
path = Path(sys.argv[2])

try:
    print(path.relative_to(root))
except ValueError:
    print(path)
PY
}

append_planner_goal_section() {
  local target_path="$1"

  if [[ -z "${PLANNER_GOAL}" || ! -f "${target_path}" ]]; then
    return 0
  fi

  SUMMARY_PATH="${target_path}" \
  PLANNER_GOAL="${PLANNER_GOAL}" \
  python3 - <<'PY'
import os
import re
from pathlib import Path

summary_path = Path(os.environ["SUMMARY_PATH"])
planner_goal = os.environ.get("PLANNER_GOAL", "")
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

write_planner_request() {
  {
    echo "## iOS AI UI Planner Request"
    echo
    echo "- Planner command: ${PLANNER_COMMAND}"
    echo "- Workspace: ${WORKSPACE_ROOT}"
    echo "- Planner context: ${PLANNER_CONTEXT_PATH}"
    if [[ -n "${EXPECTED_SCREENSHOT_PATH:-}" ]]; then
      echo "- Expected screenshot: ${EXPECTED_SCREENSHOT_PATH}"
    fi
    if [[ -n "${BEFORE_PLANNING_UI_TREE_PATH}" ]]; then
      echo "- Before-planning UI tree: $(relative_artifact_path "${BEFORE_PLANNING_UI_TREE_PATH}")"
    else
      echo "- Before-planning UI tree: unavailable"
    fi
    if [[ -n "${BEFORE_PLANNING_SCREENSHOT_PATH}" ]]; then
      echo "- Before-planning screenshot: $(relative_artifact_path "${BEFORE_PLANNING_SCREENSHOT_PATH}")"
    else
      echo "- Before-planning screenshot: unavailable"
    fi
  } > "${PLANNER_REQUEST_PATH}"

  append_planner_goal_section "${PLANNER_REQUEST_PATH}"
}

write_planner_summary() {
  if [[ "${ATTEMPTED_SOURCE}" != "ai" ]]; then
    return 0
  fi

  {
    echo "## iOS AI UI Planner"
    echo
    echo "- Result: ${STATUS}"
    echo "- Planner command: ${PLANNER_COMMAND}"
    if [[ -f "${PLANNER_REQUEST_PATH}" ]]; then
      echo "- Planner request: $(relative_artifact_path "${PLANNER_REQUEST_PATH}")"
    fi
    if [[ -f "${PLANNER_RESPONSE_JSON_PATH}" ]]; then
      echo "- Planner response JSON: $(relative_artifact_path "${PLANNER_RESPONSE_JSON_PATH}")"
    fi
    if [[ -f "${PLANNER_RESPONSE_TEXT_PATH}" ]]; then
      echo "- Planner response log: $(relative_artifact_path "${PLANNER_RESPONSE_TEXT_PATH}")"
    fi
    if [[ -f "${PLANNER_VALIDATION_ERROR_PATH}" ]]; then
      echo "- Planner validation error: $(relative_artifact_path "${PLANNER_VALIDATION_ERROR_PATH}")"
    fi
    if [[ -f "${SCENARIO_PATH}" ]]; then
      echo "- Resolved scenario: $(relative_artifact_path "${SCENARIO_PATH}")"
    else
      echo "- Resolved scenario: unavailable"
    fi
    if [[ -n "${BEFORE_PLANNING_UI_TREE_PATH}" ]]; then
      echo "- Before-planning UI tree: $(relative_artifact_path "${BEFORE_PLANNING_UI_TREE_PATH}")"
    fi
    if [[ -n "${BEFORE_PLANNING_SCREENSHOT_PATH}" ]]; then
      echo "- Before-planning screenshot: $(relative_artifact_path "${BEFORE_PLANNING_SCREENSHOT_PATH}")"
    fi
    if [[ -f "${PLANNER_NOTE_PATH}" ]]; then
      echo "- Planner note: $(relative_artifact_path "${PLANNER_NOTE_PATH}")"
    fi
    if [[ -n "${FAILURE_NOTE}" ]]; then
      echo "- Notes: ${FAILURE_NOTE}"
    fi
  } > "${PLANNER_SUMMARY_PATH}"

  append_planner_goal_section "${PLANNER_SUMMARY_PATH}"
}

write_failure_summary() {
  {
    echo "## iOS AI UI Check"
    echo
    echo "- Scenario: scenario resolution failed before runner execution"
    echo "- Result: failed"
    if [[ -n "${ATTEMPTED_SOURCE}" ]]; then
      echo "- Scenario source: ${ATTEMPTED_SOURCE}"
    fi
    if [[ -n "${FAILURE_NOTE}" ]]; then
      echo "- Notes: ${FAILURE_NOTE}"
    fi
    if [[ "${ATTEMPTED_SOURCE}" == "provided" && -n "${PROVIDED_SCENARIO_PATH}" ]]; then
      echo "- Provided scenario: ${PROVIDED_SCENARIO_PATH}"
    fi
    if [[ -f "${PLANNER_SUMMARY_PATH}" ]]; then
      echo "- Planner summary: $(relative_artifact_path "${PLANNER_SUMMARY_PATH}")"
    fi
    if [[ -f "${PLANNER_REQUEST_PATH}" ]]; then
      echo "- Planner request: $(relative_artifact_path "${PLANNER_REQUEST_PATH}")"
    fi
    if [[ -f "${PLANNER_RESPONSE_JSON_PATH}" ]]; then
      echo "- Planner response JSON: $(relative_artifact_path "${PLANNER_RESPONSE_JSON_PATH}")"
    fi
    if [[ -f "${PLANNER_RESPONSE_TEXT_PATH}" ]]; then
      echo "- Planner response log: $(relative_artifact_path "${PLANNER_RESPONSE_TEXT_PATH}")"
    fi
    if [[ -f "${PLANNER_VALIDATION_ERROR_PATH}" ]]; then
      echo "- Planner validation error: $(relative_artifact_path "${PLANNER_VALIDATION_ERROR_PATH}")"
    fi
    if [[ -n "${BEFORE_PLANNING_UI_TREE_PATH}" ]]; then
      echo "- Before-planning UI tree: $(relative_artifact_path "${BEFORE_PLANNING_UI_TREE_PATH}")"
    fi
    if [[ -n "${BEFORE_PLANNING_SCREENSHOT_PATH}" ]]; then
      echo "- Before-planning screenshot: $(relative_artifact_path "${BEFORE_PLANNING_SCREENSHOT_PATH}")"
    fi
  } > "${SUMMARY_PATH}"

  append_planner_goal_section "${SUMMARY_PATH}"
}

resolved_planner_response_path() {
  if [[ -f "${PLANNER_RESPONSE_JSON_PATH}" ]]; then
    printf '%s' "${PLANNER_RESPONSE_JSON_PATH}"
    return 0
  fi

  if [[ -f "${PLANNER_RESPONSE_TEXT_PATH}" ]]; then
    printf '%s' "${PLANNER_RESPONSE_TEXT_PATH}"
    return 0
  fi

  return 0
}

write_outputs() {
  if [[ -z "${GITHUB_OUTPUT:-}" ]]; then
    return 0
  fi

  local planner_response_path=""
  planner_response_path="$(resolved_planner_response_path)"

  {
    echo "status=${STATUS}"
    echo "scenario-path=$([[ "${STATUS}" == "passed" && -f "${SCENARIO_PATH}" ]] && printf '%s' "${SCENARIO_PATH}")"
    echo "summary-path=$([[ -f "${SUMMARY_PATH}" ]] && printf '%s' "${SUMMARY_PATH}")"
    echo "resolved-source=${RESOLVED_SOURCE}"
    echo "failure-note=${FAILURE_NOTE}"
    echo "before-planning-ui-tree-path=${BEFORE_PLANNING_UI_TREE_PATH}"
    echo "before-planning-screenshot-path=${BEFORE_PLANNING_SCREENSHOT_PATH}"
    echo "current-ui-tree-path=${BEFORE_PLANNING_UI_TREE_PATH}"
    echo "current-screenshot-path=${BEFORE_PLANNING_SCREENSHOT_PATH}"
    echo "planner-note-path=$([[ -f "${PLANNER_NOTE_PATH}" ]] && printf '%s' "${PLANNER_NOTE_PATH}")"
    echo "planner-request-path=$([[ -f "${PLANNER_REQUEST_PATH}" ]] && printf '%s' "${PLANNER_REQUEST_PATH}")"
    echo "planner-response-path=${planner_response_path}"
    echo "planner-validation-error-path=$([[ -f "${PLANNER_VALIDATION_ERROR_PATH}" ]] && printf '%s' "${PLANNER_VALIDATION_ERROR_PATH}")"
    echo "planner-summary-path=$([[ -f "${PLANNER_SUMMARY_PATH}" ]] && printf '%s' "${PLANNER_SUMMARY_PATH}")"
  } >> "${GITHUB_OUTPUT}"
}

cleanup() {
  trim_file_if_empty "${PLANNER_RESPONSE_TEXT_PATH}"
  trim_file_if_empty "${PLANNER_RESPONSE_JSON_PATH}"
  trim_file_if_empty "${PLANNER_VALIDATION_ERROR_PATH}"

  write_planner_summary

  if [[ "${STATUS}" != "passed" ]]; then
    write_failure_summary
  fi

  write_outputs
}

trap cleanup EXIT

validate_json() {
  python3 "${AI_UI_CONTRACT_SCRIPT}" validate-scenario "$1"
}

validate_accessibility_ids() {
  local ui_tree_arg=()
  if [[ -n "${BEFORE_PLANNING_UI_TREE_PATH:-}" ]]; then
    ui_tree_arg=(--before-planning-ui-tree "${BEFORE_PLANNING_UI_TREE_PATH}")
  fi

  python3 "${AI_UI_CONTRACT_SCRIPT}" validate-generated-scenario \
    "$1" \
    --repo-root "${WORKSPACE_ROOT}" \
    --planner-context "${PLANNER_CONTEXT_PATH}" \
    --config-dir "${AI_UI_CONFIG_DIR}" \
    "${ui_tree_arg[@]}"
}

run_live_inspection() {
  if [[ -z "${ACTION_ROOT}" || -z "${SIMULATOR_NAME}" ]]; then
    echo "Skipping live inspection before planning because action context is incomplete." >&2
    return 0
  fi

  if [[ ! -f "${RUNNER_SCRIPT}" ]]; then
    echo "Skipping live inspection before planning because runner script was not found: ${RUNNER_SCRIPT}" >&2
    return 0
  fi

  local inspect_dir="${ARTIFACTS_DIR}/inspect"
  local simulator_env_path="${inspect_dir}/simulator.env"
  mkdir -p "${inspect_dir}"

  if ! "${ACTION_ROOT}/scripts/boot-simulator.sh" "${simulator_env_path}"; then
    echo "Skipping live inspection before planning because simulator bootstrap failed." >&2
    return 0
  fi

  if [[ ! -f "${simulator_env_path}" ]]; then
    echo "Skipping live inspection before planning because simulator bootstrap did not produce ${simulator_env_path}." >&2
    return 0
  fi

  if ! source "${simulator_env_path}"; then
    echo "Skipping live inspection before planning because ${simulator_env_path} could not be loaded." >&2
    return 0
  fi

  BEFORE_PLANNING_UI_TREE_PATH="${inspect_dir}/before-planning-ui-tree.json"
  BEFORE_PLANNING_SCREENSHOT_PATH="${inspect_dir}/before-planning-screenshot.png"

  set +e
  AI_UI_ARTIFACTS_DIR="${inspect_dir}" \
  AI_UI_SIMULATOR_NAME="${SIMULATOR_NAME}" \
  AI_UI_SIMULATOR_RUNTIME="${SIMULATOR_RUNTIME}" \
  AI_UI_SIMULATOR_UDID="${AI_UI_SIMULATOR_UDID}" \
  AI_UI_SIMULATOR_RUNTIME_NAME="${AI_UI_SIMULATOR_RUNTIME_NAME}" \
  AI_UI_BEFORE_PLANNING_UI_TREE_PATH="${BEFORE_PLANNING_UI_TREE_PATH}" \
  AI_UI_BEFORE_PLANNING_SCREENSHOT_PATH="${BEFORE_PLANNING_SCREENSHOT_PATH}" \
  AI_UI_CURRENT_UI_TREE_PATH="${BEFORE_PLANNING_UI_TREE_PATH}" \
  AI_UI_CURRENT_SCREENSHOT_PATH="${BEFORE_PLANNING_SCREENSHOT_PATH}" \
  python3 - "${MAX_DURATION_SECONDS}" "${RUNNER_SCRIPT}" <<'PY'
import os
import subprocess
import sys

timeout = int(sys.argv[1])
script = sys.argv[2]

try:
    completed = subprocess.run(
        ["/bin/bash", script, "inspect"],
        env=os.environ.copy(),
        timeout=timeout,
        check=False,
    )
    sys.exit(completed.returncode)
except subprocess.TimeoutExpired:
    sys.stderr.write(f"Runner inspect timed out after {timeout} seconds\n")
    sys.exit(124)
PY
  inspect_exit="$?"
  set -e

  if [[ "${inspect_exit}" -ne 0 ]]; then
    echo "Live inspection before planning failed with exit code ${inspect_exit}. Continuing with static planner context." >&2
  fi

  if [[ ! -f "${BEFORE_PLANNING_UI_TREE_PATH}" ]]; then
    BEFORE_PLANNING_UI_TREE_PATH=""
  fi

  if [[ ! -f "${BEFORE_PLANNING_SCREENSHOT_PATH}" ]]; then
    BEFORE_PLANNING_SCREENSHOT_PATH=""
  fi
}

validate_planner_output() {
  rm -f "${PLANNER_VALIDATION_ERROR_PATH}"

  if [[ ! -f "${SCENARIO_PATH}" ]]; then
    if [[ -f "${PLANNER_RESPONSE_JSON_PATH}" ]]; then
      {
        printf 'planner-command did not create validated scenario JSON at %s\n' "${SCENARIO_PATH}"
        printf 'raw planner draft was preserved at %s\n' "${PLANNER_RESPONSE_JSON_PATH}"
      } > "${PLANNER_VALIDATION_ERROR_PATH}"
    else
      printf 'planner-command did not create scenario JSON at %s\n' "${SCENARIO_PATH}" \
        > "${PLANNER_VALIDATION_ERROR_PATH}"
    fi
    FAILURE_NOTE="Planner command completed without producing scenario JSON."
    return 1
  fi

  if ! validate_json "${SCENARIO_PATH}" 2>"${PLANNER_VALIDATION_ERROR_PATH}"; then
    FAILURE_NOTE="Planner generated scenario JSON that did not match the scenario contract."
    return 1
  fi

  if ! validate_accessibility_ids "${SCENARIO_PATH}" 2>"${PLANNER_VALIDATION_ERROR_PATH}"; then
    FAILURE_NOTE="Planner generated a scenario that failed accessibility or conditional-state validation."
    return 1
  fi

  if [[ ! -f "${PLANNER_RESPONSE_JSON_PATH}" ]]; then
    cp "${SCENARIO_PATH}" "${PLANNER_RESPONSE_JSON_PATH}"
  fi

  rm -f "${PLANNER_VALIDATION_ERROR_PATH}"
  return 0
}

use_provided() {
  local scenario_file="$1"

  ATTEMPTED_SOURCE="provided"

  if [[ ! -f "${scenario_file}" ]]; then
    FAILURE_NOTE="Provided scenario file not found: ${scenario_file}"
    return 1
  fi

  cp "${scenario_file}" "${SCENARIO_PATH}"
  if ! validate_json "${SCENARIO_PATH}"; then
    FAILURE_NOTE="Provided scenario JSON did not match the scenario contract."
    rm -f "${SCENARIO_PATH}"
    return 1
  fi

  RESOLVED_SOURCE="provided"
  STATUS="passed"
  return 0
}

run_planner() {
  ATTEMPTED_SOURCE="ai"

  if [[ -z "${PLANNER_COMMAND}" ]]; then
    FAILURE_NOTE="No provided scenario was found and planner-command is not set."
    return 1
  fi

  run_live_inspection || true
  write_planner_request

  set +e
  AI_UI_SCENARIO_OUTPUT_PATH="${SCENARIO_PATH}" \
  AI_UI_PLANNER_DRAFT_SCENARIO_PATH="${PLANNER_RESPONSE_JSON_PATH}" \
  AI_UI_PLANNER_GOAL="${PLANNER_GOAL:-}" \
  AI_UI_EXPECTED_SCREENSHOT_PATH="${EXPECTED_SCREENSHOT_PATH:-}" \
  AI_UI_BEFORE_PLANNING_UI_TREE_PATH="${BEFORE_PLANNING_UI_TREE_PATH:-}" \
  AI_UI_BEFORE_PLANNING_SCREENSHOT_PATH="${BEFORE_PLANNING_SCREENSHOT_PATH:-}" \
  AI_UI_CURRENT_UI_TREE_PATH="${BEFORE_PLANNING_UI_TREE_PATH:-}" \
  AI_UI_CURRENT_SCREENSHOT_PATH="${BEFORE_PLANNING_SCREENSHOT_PATH:-}" \
  AI_UI_EVENT_PATH="${GITHUB_EVENT_PATH:-}" \
  AI_UI_REPOSITORY="${GITHUB_REPOSITORY:-}" \
  AI_UI_PLANNER_NOTE_OUTPUT_PATH="${PLANNER_NOTE_PATH}" \
  AI_UI_WORKSPACE="${GITHUB_WORKSPACE:-$PWD}" \
  bash -c "${PLANNER_COMMAND}" >"${PLANNER_RESPONSE_TEXT_PATH}" 2>&1
  local planner_exit="$?"
  set -e

  trim_file_if_empty "${PLANNER_RESPONSE_TEXT_PATH}"

  if [[ "${planner_exit}" -ne 0 ]]; then
    FAILURE_NOTE="Planner command failed with exit code ${planner_exit}."
    return 1
  fi

  if ! validate_planner_output; then
    return 1
  fi

  RESOLVED_SOURCE="ai"
  STATUS="passed"
  return 0
}

main() {
  local resolved_provided_path=""

  STATUS="failed"

  if [[ -n "${PROVIDED_SCENARIO_PATH}" && -f "${PROVIDED_SCENARIO_PATH}" ]]; then
    resolved_provided_path="${PROVIDED_SCENARIO_PATH}"
  fi

  if [[ -n "${resolved_provided_path}" ]]; then
    use_provided "${resolved_provided_path}"
    return 0
  fi

  run_planner
}

if ! main; then
  STATUS="failed"
fi

exit 0
