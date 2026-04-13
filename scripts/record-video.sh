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
    rm -f "${VIDEO_PATH}"

    xcrun simctl io "${UDID}" recordVideo --codec=h264 "${VIDEO_PATH}" >/dev/null 2>&1 &
    echo "$!" > "${PID_FILE}"
    ;;
  stop)
    if [[ ! -f "${PID_FILE}" ]]; then
      exit 0
    fi

    PID="$(cat "${PID_FILE}")"
    kill -INT "${PID}" >/dev/null 2>&1 || true
    wait "${PID}" 2>/dev/null || true
    rm -f "${PID_FILE}"
    ;;
  *)
    echo "Unsupported mode: ${MODE}" >&2
    exit 1
    ;;
esac
