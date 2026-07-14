#!/usr/bin/env bash

set -euo pipefail

MODE="${1:?MODE is required}"
PID_FILE="${2:?PID_FILE is required}"
UDID="${3:-}"
VIDEO_PATH="${4:-}"

case "${MODE}" in
  start)
    if [[ -z "${UDID}" || -z "${VIDEO_PATH}" ]]; then
      echo "UDID and VIDEO_PATH are required for start mode" >&2
      exit 1
    fi

    mkdir -p "$(dirname "${VIDEO_PATH}")"
    mkdir -p "$(dirname "${PID_FILE}")"
    rm -f "${PID_FILE}" "${VIDEO_PATH}"

    python3 - "${PID_FILE}" "${UDID}" "${VIDEO_PATH}" <<'PY'
import os
import pathlib
import signal
import subprocess
import sys
import time

pid_path, udid, video_path = sys.argv[1:4]


def signal_process_group(process, signal_number):
    try:
        os.killpg(process.pid, signal_number)
    except ProcessLookupError:
        pass


def process_group_exists(process):
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop_process_group(process):
    try:
        grace = float(os.environ.get("AI_UI_VIDEO_START_CLEANUP_TIMEOUT_SECONDS", "5"))
    except ValueError:
        grace = 5.0
    if grace < 0:
        grace = 5.0

    signal_process_group(process, signal.SIGTERM)
    deadline = time.monotonic() + grace
    while process_group_exists(process) and time.monotonic() < deadline:
        if process.poll() is None:
            try:
                process.wait(timeout=min(0.05, max(0.0, deadline - time.monotonic())))
            except subprocess.TimeoutExpired:
                pass
        else:
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

    if process_group_exists(process):
        signal_process_group(process, signal.SIGKILL)

    if process.poll() is None:
        process.wait()


with open("/dev/null", "rb") as stdin, open("/dev/null", "ab") as output:
    process = subprocess.Popen(
        ["xcrun", "simctl", "io", udid, "recordVideo", "--codec=h264", video_path],
        stdin=stdin,
        stdout=output,
        stderr=output,
        start_new_session=True,
    )

try:
    pathlib.Path(pid_path).write_text(f"{process.pid}\n", encoding="utf-8")
except BaseException:
    stop_process_group(process)
    raise
PY
    ;;
  stop)
    if [[ ! -f "${PID_FILE}" ]]; then
      exit 0
    fi

    PID="$(tr -d '[:space:]' < "${PID_FILE}")"
    if [[ ! "${PID}" =~ ^[1-9][0-9]*$ ]]; then
      echo "Invalid video recorder PID: ${PID}" >&2
      rm -f "${PID_FILE}"
      exit 1
    fi

    if ! kill -0 -- "-${PID}" >/dev/null 2>&1; then
      echo "Video recorder exited before finalization was requested." >&2
      rm -f "${PID_FILE}"
      exit 1
    fi

    STOP_TIMEOUT_SECONDS="${AI_UI_VIDEO_STOP_TIMEOUT_SECONDS:-30}"
    FORCE_STOP_TIMEOUT_SECONDS="${AI_UI_VIDEO_FORCE_STOP_TIMEOUT_SECONDS:-5}"
    if [[ ! "${STOP_TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ || ! "${FORCE_STOP_TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]]; then
      echo "Video stop timeouts must be positive integers" >&2
      exit 1
    fi

    wait_for_exit() {
      local timeout_seconds="$1"
      local deadline=$((SECONDS + timeout_seconds))
      while kill -0 -- "-${PID}" >/dev/null 2>&1; do
        if [[ "${SECONDS}" -ge "${deadline}" ]]; then
          return 1
        fi
        sleep 0.2
      done
      return 0
    }

    kill -INT -- "-${PID}" >/dev/null 2>&1 || true
    if ! wait_for_exit "${STOP_TIMEOUT_SECONDS}"; then
      echo "Video recorder did not finalize after SIGINT; sending SIGTERM." >&2
      kill -TERM -- "-${PID}" >/dev/null 2>&1 || true
      if ! wait_for_exit "${FORCE_STOP_TIMEOUT_SECONDS}"; then
        echo "Video recorder did not stop after SIGTERM; sending SIGKILL." >&2
        kill -KILL -- "-${PID}" >/dev/null 2>&1 || true
      fi
      rm -f "${PID_FILE}"
      exit 1
    fi

    rm -f "${PID_FILE}"
    ;;
  *)
    echo "Unsupported mode: ${MODE}" >&2
    exit 1
    ;;
esac
