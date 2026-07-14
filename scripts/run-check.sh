#!/usr/bin/env bash

set -euo pipefail

ACTION_ROOT="${ACTION_ROOT:?ACTION_ROOT is required}"
RUNNER_SCRIPT="${RUNNER_SCRIPT:?RUNNER_SCRIPT is required}"
ARTIFACTS_DIR="${ARTIFACTS_DIR:?ARTIFACTS_DIR is required}"
SCENARIO_PATH="${SCENARIO_PATH:?SCENARIO_PATH is required}"
SIMULATOR_NAME="${SIMULATOR_NAME:?SIMULATOR_NAME is required}"
SIMULATOR_RUNTIME="${SIMULATOR_RUNTIME:-26.2}"
RECORD_VIDEO="${RECORD_VIDEO:-true}"
MAX_DURATION_SECONDS="${MAX_DURATION_SECONDS:-300}"
PLANNER_GOAL="${PLANNER_GOAL:-}"

absolute_path() {
  python3 - "$1" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).expanduser().resolve(strict=False))
PY
}

ARTIFACTS_DIR="$(absolute_path "${ARTIFACTS_DIR}")"
SCENARIO_PATH="$(absolute_path "${SCENARIO_PATH}")"
if [[ -n "${PLANNER_NOTE_PATH:-}" ]]; then
  PLANNER_NOTE_PATH="$(absolute_path "${PLANNER_NOTE_PATH}")"
fi
if [[ -n "${EXPECTED_SCREENSHOT_PATH:-}" ]]; then
  EXPECTED_SCREENSHOT_PATH="$(absolute_path "${EXPECTED_SCREENSHOT_PATH}")"
fi

mkdir -p "${ARTIFACTS_DIR}"

SIMULATOR_ENV_PATH="${ARTIFACTS_DIR}/simulator.env"
SUMMARY_PATH="${ARTIFACTS_DIR}/summary.md"
VIDEO_RECORDING_PATH="${ARTIFACTS_DIR}/run.mp4"
VIDEO_PID_PATH="${ARTIFACTS_DIR}/record-video.pid"
FAILURE_SCREENSHOT_PATH="${ARTIFACTS_DIR}/failure-screenshot.png"

STATUS="passed"
RUNNER_EXIT=0
FAILURE_NOTE=""
VIDEO_PATH=""
VIDEO_NOTE=""
VIDEO_RECORDING_STARTED="false"

simulator_summary() {
  if [[ -n "${AI_UI_SIMULATOR_DEVICE_NAME:-}" && -n "${AI_UI_SIMULATOR_RUNTIME_NAME:-}" ]]; then
    printf '%s (%s)\n' "${AI_UI_SIMULATOR_DEVICE_NAME}" "${AI_UI_SIMULATOR_RUNTIME_NAME}"
    return 0
  fi

  printf '%s (iOS %s)\n' "${SIMULATOR_NAME}" "${SIMULATOR_RUNTIME}"
}

write_default_summary() {
  {
    echo "## iOS AI UI Check"
    echo
    echo "- Status: ${STATUS}"
    echo "- Scenario: ${SCENARIO_PATH}"
    echo "- Simulator: $(simulator_summary)"
    echo "- Runner script: ${RUNNER_SCRIPT}"
    echo "- Artifacts dir: ${ARTIFACTS_DIR}"
    if [[ -n "${VIDEO_PATH}" ]]; then
      echo "- Video: ${VIDEO_PATH}"
    elif [[ "${RECORD_VIDEO}" == "true" ]]; then
      echo "- Video: requested but not captured"
    fi
    if [[ -n "${EXPECTED_SCREENSHOT_PATH:-}" ]]; then
      echo "- Expected screenshot: ${EXPECTED_SCREENSHOT_PATH}"
    fi
    if [[ "${RUNNER_EXIT}" -ne 0 ]]; then
      echo "- Runner exit code: ${RUNNER_EXIT}"
    fi
    if [[ -n "${FAILURE_NOTE}" ]]; then
      echo "- Notes: ${FAILURE_NOTE}"
    fi
  } > "${SUMMARY_PATH}"
}

append_planner_goal_to_summary() {
  if [[ -z "${PLANNER_GOAL}" || ! -f "${SUMMARY_PATH}" ]]; then
    return 0
  fi

  SUMMARY_PATH="${SUMMARY_PATH}" \
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

append_planner_note_to_summary() {
  if [[ -z "${PLANNER_NOTE_PATH:-}" || ! -f "${PLANNER_NOTE_PATH}" || ! -f "${SUMMARY_PATH}" ]]; then
    return 0
  fi

  SUMMARY_PATH="${SUMMARY_PATH}" \
  PLANNER_NOTE_PATH="${PLANNER_NOTE_PATH}" \
  python3 - <<'PY'
import os
from pathlib import Path

summary_path = Path(os.environ["SUMMARY_PATH"])
planner_note_path = Path(os.environ["PLANNER_NOTE_PATH"])
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

extract_failure_screenshot_from_xcresult() {
  if [[ "${STATUS}" != "failed" ]]; then
    return 0
  fi

  rm -f "${FAILURE_SCREENSHOT_PATH}"

  extract_failure_screenshot_via_sqlite() {
    local xcresult_path="$1"
    local database_path="${xcresult_path}/database.sqlite3"
    [[ -f "${database_path}" ]] || return 1
    command -v sqlite3 >/dev/null 2>&1 || return 1

    local query_result
    query_result="$(
      sqlite3 -separator '|' "${database_path}" \
        "SELECT filenameOverride, xcResultKitPayloadRefId FROM Attachments WHERE name = 'Failure Screenshot' AND uniformTypeIdentifier = 'public.png' ORDER BY timestamp DESC LIMIT 1;" \
        2>/dev/null || true
    )"
    [[ -n "${query_result}" ]] || return 1

    local payload_ref="${query_result#*|}"
    [[ -n "${payload_ref}" && "${payload_ref}" != "${query_result}" ]] || return 1

    local blob_path="${xcresult_path}/Data/data.${payload_ref}"
    [[ -f "${blob_path}" ]] || return 1

    cp "${blob_path}" "${FAILURE_SCREENSHOT_PATH}"
    return 0
  }

  extract_failure_screenshot_via_xcresulttool() {
    local xcresult_path="$1"
    command -v xcrun >/dev/null 2>&1 || return 1

    local export_dir
    export_dir="$(mktemp -d "${TMPDIR:-/tmp}/ios-ai-ui-check-attachments.XXXXXX")"

    if ! xcrun xcresulttool export attachments --path "${xcresult_path}" --output-path "${export_dir}" >/dev/null 2>&1; then
      rm -rf "${export_dir}"
      return 1
    fi

    local manifest_path="${export_dir}/manifest.json"
    if [[ ! -f "${manifest_path}" ]]; then
      rm -rf "${export_dir}"
      return 1
    fi

    local exported_file
    exported_file="$(
      python3 - "${manifest_path}" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
payload = json.loads(manifest_path.read_text(encoding="utf-8"))

candidates = []
for test_entry in payload:
    for attachment in test_entry.get("attachments", []):
        suggested_name = attachment.get("suggestedHumanReadableName", "")
        exported_file_name = attachment.get("exportedFileName", "")
        if not exported_file_name:
            continue
        if not suggested_name.lower().startswith("failure screenshot"):
            continue
        candidates.append((attachment.get("timestamp", 0), exported_file_name))

if candidates:
    candidates.sort()
    print(candidates[-1][1])
PY
    )"

    if [[ -n "${exported_file}" && -f "${export_dir}/${exported_file}" ]]; then
      cp "${export_dir}/${exported_file}" "${FAILURE_SCREENSHOT_PATH}"
      rm -rf "${export_dir}"
      return 0
    fi

    rm -rf "${export_dir}"
    return 1
  }

  local xcresult_path
  while IFS= read -r xcresult_path; do
    extract_failure_screenshot_via_sqlite "${xcresult_path}" && return 0
    extract_failure_screenshot_via_xcresulttool "${xcresult_path}" && return 0
  done < <(find "${ARTIFACTS_DIR}" -maxdepth 2 -type d -name '*.xcresult' | sort)
}

append_failure_screenshot_to_summary() {
  if [[ ! -f "${SUMMARY_PATH}" || ! -f "${FAILURE_SCREENSHOT_PATH}" ]]; then
    return 0
  fi

  if grep -q "^- Failure screenshot:" "${SUMMARY_PATH}"; then
    return 0
  fi

  printf '\n- Failure screenshot: %s\n' "$(basename "${FAILURE_SCREENSHOT_PATH}")" >> "${SUMMARY_PATH}"
}

append_video_note_to_summary() {
  if [[ -z "${VIDEO_NOTE}" || ! -f "${SUMMARY_PATH}" ]]; then
    return 0
  fi

  if grep -q "^- Video note:" "${SUMMARY_PATH}"; then
    return 0
  fi

  printf '\n- Video note: %s\n' "${VIDEO_NOTE}" >> "${SUMMARY_PATH}"
}

remove_transient_video_sidecars() {
  if [[ -z "${VIDEO_RECORDING_PATH}" ]]; then
    return 0
  fi

  shopt -s nullglob
  local sidecars=("${VIDEO_RECORDING_PATH}".sb-*)
  if (( ${#sidecars[@]} > 0 )); then
    rm -f "${sidecars[@]}"
  fi
  shopt -u nullglob
}

ensure_failed_summary_is_consistent() {
  if [[ "${STATUS}" != "failed" || ! -f "${SUMMARY_PATH}" ]]; then
    return 0
  fi

  SUMMARY_PATH="${SUMMARY_PATH}" \
  RUNNER_EXIT="${RUNNER_EXIT}" \
  FAILURE_NOTE="${FAILURE_NOTE}" \
  python3 - <<'PY'
import os
import re
from pathlib import Path

summary_path = Path(os.environ["SUMMARY_PATH"])
runner_exit = os.environ.get("RUNNER_EXIT", "")
failure_note = os.environ.get("FAILURE_NOTE", "").strip()
summary_text = summary_path.read_text(encoding="utf-8")
lines = summary_text.splitlines()
found_outcome = False

for index, line in enumerate(lines):
    match = re.match(
        r"^(\s*(?:(?:[-*]\s*)|(?:#{1,6}\s*))?(?:Status|Result):)\s*.*$",
        line,
        flags=re.IGNORECASE,
    )
    if match:
        lines[index] = f"{match.group(1)} failed"
        found_outcome = True

if not found_outcome:
    outcome_lines = ["## Action Outcome", "", "- Status: failed"]
    if lines:
        outcome_lines.append("")
    lines = outcome_lines + lines

runner_exit_line = f"- Runner exit code: {runner_exit}" if runner_exit else ""
if runner_exit_line and runner_exit_line not in lines:
    lines.append(runner_exit_line)

failure_note_line = f"- Notes: {failure_note}" if failure_note else ""
if failure_note_line and failure_note_line not in lines:
    lines.append(failure_note_line)

summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

cleanup() {
  if [[ "${VIDEO_RECORDING_STARTED}" == "true" ]]; then
    if "${ACTION_ROOT}/scripts/record-video.sh" stop "${VIDEO_PID_PATH}"; then
      if [[ -f "${VIDEO_RECORDING_PATH}" && -s "${VIDEO_RECORDING_PATH}" ]]; then
        VIDEO_PATH="${VIDEO_RECORDING_PATH}"
      else
        VIDEO_NOTE="Video recording did not produce a non-empty finalized file; the video output was omitted."
        rm -f "${VIDEO_RECORDING_PATH}" || true
      fi
    else
      VIDEO_NOTE="Video recording did not finalize successfully; the video output was omitted."
      rm -f "${VIDEO_RECORDING_PATH}" || true
    fi
    remove_transient_video_sidecars || true
  fi

  if [[ ! -f "${SUMMARY_PATH}" ]]; then
    write_default_summary
  fi

  ensure_failed_summary_is_consistent

  extract_failure_screenshot_from_xcresult
  append_failure_screenshot_to_summary
  append_video_note_to_summary
  append_planner_goal_to_summary
  append_planner_note_to_summary

  {
    echo "status=${STATUS}"
    echo "summary-path=${SUMMARY_PATH}"
    echo "video-path=${VIDEO_PATH}"
    echo "failure-note=${FAILURE_NOTE}"
  } >> "${GITHUB_OUTPUT}"
}

trap cleanup EXIT

if [[ ! "${MAX_DURATION_SECONDS}" =~ ^[1-9][0-9]*$ ]]; then
  echo "max-duration-seconds must be a positive integer: ${MAX_DURATION_SECONDS}" >&2
  RUNNER_EXIT=2
  STATUS="failed"
  FAILURE_NOTE="max-duration-seconds must be a positive integer."
  exit 0
fi

if [[ ! -f "${RUNNER_SCRIPT}" ]]; then
  echo "Runner script not found: ${RUNNER_SCRIPT}" >&2
  RUNNER_EXIT=127
  STATUS="failed"
  FAILURE_NOTE="Runner failed before producing its own summary."
  exit 0
fi

if [[ ! -f "${SCENARIO_PATH}" ]]; then
  echo "Scenario file not found: ${SCENARIO_PATH}" >&2
  RUNNER_EXIT=1
  STATUS="failed"
  FAILURE_NOTE="Scenario file was missing before runner execution."
  exit 0
fi

if ! "${ACTION_ROOT}/scripts/boot-simulator.sh" "${SIMULATOR_ENV_PATH}"; then
  echo "Simulator bootstrap failed." >&2
  RUNNER_EXIT=1
  STATUS="failed"
  FAILURE_NOTE="Simulator bootstrap failed before runner execution."
  exit 0
fi

if [[ ! -f "${SIMULATOR_ENV_PATH}" ]]; then
  echo "Simulator bootstrap did not produce ${SIMULATOR_ENV_PATH}." >&2
  RUNNER_EXIT=1
  STATUS="failed"
  FAILURE_NOTE="Simulator bootstrap did not produce the expected environment file."
  exit 0
fi

if ! source "${SIMULATOR_ENV_PATH}"; then
  echo "Failed to load simulator environment from ${SIMULATOR_ENV_PATH}." >&2
  RUNNER_EXIT=1
  STATUS="failed"
  FAILURE_NOTE="Simulator bootstrap produced an unreadable environment file."
  exit 0
fi

export AI_UI_SCENARIO_PATH="${SCENARIO_PATH}"
export AI_UI_ARTIFACTS_DIR="${ARTIFACTS_DIR}"
export AI_UI_EXPECTED_SCREENSHOT_PATH="${EXPECTED_SCREENSHOT_PATH:-}"
export AI_UI_SIMULATOR_NAME="${SIMULATOR_NAME}"
export AI_UI_SIMULATOR_RUNTIME="${SIMULATOR_RUNTIME}"
export AI_UI_SIMULATOR_UDID="${AI_UI_SIMULATOR_UDID}"
export AI_UI_SIMULATOR_RUNTIME_NAME="${AI_UI_SIMULATOR_RUNTIME_NAME}"
export AI_UI_MAX_DURATION_SECONDS="${MAX_DURATION_SECONDS}"
export AI_UI_PLANNER_GOAL="${PLANNER_GOAL}"

if [[ "${RECORD_VIDEO}" == "true" ]]; then
  if "${ACTION_ROOT}/scripts/record-video.sh" start "${VIDEO_PID_PATH}" "${AI_UI_SIMULATOR_UDID}" "${VIDEO_RECORDING_PATH}"; then
    VIDEO_RECORDING_STARTED="true"
  else
    VIDEO_NOTE="Video recording failed to start; the UI check continued without video."
    rm -f "${VIDEO_PID_PATH}" "${VIDEO_RECORDING_PATH}" || true
    remove_transient_video_sidecars || true
  fi
fi

set +e
python3 "${ACTION_ROOT}/scripts/run-with-timeout.py" \
  --timeout "${MAX_DURATION_SECONDS}" \
  --label "Runner" \
  -- /bin/bash "${RUNNER_SCRIPT}"
RUNNER_EXIT="$?"
set -e

if [[ "${RUNNER_EXIT}" -ne 0 ]]; then
  STATUS="failed"
  if [[ "${RUNNER_EXIT}" -eq 124 ]]; then
    FAILURE_NOTE="Runner timed out after ${MAX_DURATION_SECONDS} seconds."
  else
    FAILURE_NOTE="Runner exited with code ${RUNNER_EXIT}."
  fi
fi

exit 0
