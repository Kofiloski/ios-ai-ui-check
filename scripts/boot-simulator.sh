#!/usr/bin/env bash

set -euo pipefail

OUTPUT_ENV_FILE="${1:?OUTPUT_ENV_FILE is required}"
SIMULATOR_NAME="${SIMULATOR_NAME:?SIMULATOR_NAME is required}"
SIMULATOR_RUNTIME="${SIMULATOR_RUNTIME:-26.2}"

if [[ -n "${AI_UI_SIMULATOR_UDID:-}" && -n "${AI_UI_SIMULATOR_DEVICE_NAME:-}" && -n "${AI_UI_SIMULATOR_RUNTIME_ID:-}" && -n "${AI_UI_SIMULATOR_RUNTIME_NAME:-}" ]]; then
  cat > "${OUTPUT_ENV_FILE}" <<EOF
export AI_UI_SIMULATOR_UDID='${AI_UI_SIMULATOR_UDID}'
export AI_UI_SIMULATOR_DEVICE_NAME='${AI_UI_SIMULATOR_DEVICE_NAME}'
export AI_UI_SIMULATOR_RUNTIME_ID='${AI_UI_SIMULATOR_RUNTIME_ID}'
export AI_UI_SIMULATOR_RUNTIME_NAME='${AI_UI_SIMULATOR_RUNTIME_NAME}'
EOF

  xcrun simctl boot "${AI_UI_SIMULATOR_UDID}" >/dev/null 2>&1 || true
  xcrun simctl bootstatus "${AI_UI_SIMULATOR_UDID}" -b
  exit 0
fi

TMP_JSON="$(mktemp)"
trap 'rm -f "${TMP_JSON}"' EXIT

xcrun simctl list devices available -j > "${TMP_JSON}"

python3 - "${TMP_JSON}" "${SIMULATOR_NAME}" "${SIMULATOR_RUNTIME}" "${OUTPUT_ENV_FILE}" <<'PY'
import json
import re
import shlex
import sys

json_path, simulator_name, simulator_runtime, output_env_path = sys.argv[1:5]

with open(json_path, "r", encoding="utf-8") as handle:
    payload = json.load(handle)

devices_by_runtime = payload.get("devices", {})

def parse_version(runtime_id: str) -> tuple[int, ...]:
    match = re.search(r"iOS[- ](.+)$", runtime_id)
    if not match:
        return tuple()
    raw = match.group(1).replace("-", ".")
    parts = []
    for token in raw.split("."):
        if token.isdigit():
            parts.append(int(token))
    return tuple(parts)

def normalize_runtime_filter(value: str) -> str:
    text = value.strip().lower()
    text = text.removeprefix("ios").strip()
    text = text.replace(" ", "").replace(".", "-")
    return text

def human_runtime_name(runtime_id: str) -> str:
    raw = runtime_id.split(".")[-1]
    if raw.startswith("iOS-"):
        return "iOS " + raw.removeprefix("iOS-").replace("-", ".")
    return raw.replace("-", ".")

target = normalize_runtime_filter(simulator_runtime)
candidates = []

for runtime_id, devices in devices_by_runtime.items():
    if "iOS" not in runtime_id:
        continue
    if not runtime_id.lower().endswith(target):
        continue
    for device in devices:
        if not device.get("isAvailable", False):
            continue
        if device.get("name") != simulator_name:
            continue
        candidates.append(
            {
                "runtime_id": runtime_id,
                "runtime_name": human_runtime_name(runtime_id),
                "device_name": device["name"],
                "udid": device["udid"],
                "version": parse_version(runtime_id),
            }
        )

if not candidates:
    raise SystemExit(
        f"No available simulator matched name={simulator_name!r} runtime={simulator_runtime!r}"
    )

selected = sorted(candidates, key=lambda item: item["version"], reverse=True)[0]

with open(output_env_path, "w", encoding="utf-8") as handle:
    for key, value in (
        ("AI_UI_SIMULATOR_UDID", selected["udid"]),
        ("AI_UI_SIMULATOR_DEVICE_NAME", selected["device_name"]),
        ("AI_UI_SIMULATOR_RUNTIME_ID", selected["runtime_id"]),
        ("AI_UI_SIMULATOR_RUNTIME_NAME", selected["runtime_name"]),
    ):
        handle.write(f"export {key}={shlex.quote(value)}\n")
PY

# shellcheck disable=SC1090
source "${OUTPUT_ENV_FILE}"

xcrun simctl boot "${AI_UI_SIMULATOR_UDID}" >/dev/null 2>&1 || true
xcrun simctl bootstatus "${AI_UI_SIMULATOR_UDID}" -b
