#!/usr/bin/env bash

set -euo pipefail

COMMENT_MARKER="<!-- ios-ai-ui-check:managed-comment -->"
export COMMENT_MARKER

if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "GITHUB_TOKEN is not available. Skipping PR comment."
  exit 0
fi

if [[ -z "${GITHUB_EVENT_PATH:-}" || ! -f "${GITHUB_EVENT_PATH}" ]]; then
  echo "GITHUB_EVENT_PATH is not available. Skipping PR comment."
  exit 0
fi

PR_NUMBER="$(python3 - "${GITHUB_EVENT_PATH}" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    payload = json.load(handle)

pull_request = payload.get("pull_request")
if not pull_request:
    raise SystemExit("")

print(pull_request["number"])
PY
)"

if [[ -z "${PR_NUMBER}" ]]; then
  echo "No pull request number found. Skipping PR comment."
  exit 0
fi

SUMMARY_BODY=""
if [[ -n "${SUMMARY_PATH:-}" && -f "${SUMMARY_PATH}" ]]; then
  SUMMARY_BODY="$(cat "${SUMMARY_PATH}")"
else
  SUMMARY_BODY="No summary was generated."
fi
export SUMMARY_BODY

ARTIFACT_LINE="Artifact upload disabled or unavailable."
if [[ -n "${ARTIFACT_URL:-}" ]]; then
  ARTIFACT_LINE="[${ARTIFACT_NAME:-ios-ai-ui-check}](${ARTIFACT_URL})"
fi
export ARTIFACT_LINE

PAYLOAD_PATH="$(mktemp)"
COMMENTS_PATH="$(mktemp)"
trap 'rm -f "${PAYLOAD_PATH}" "${COMMENTS_PATH}"' EXIT

python3 - "${PAYLOAD_PATH}" <<'PY'
import json
import os
import sys

payload_path = sys.argv[1]
comment_marker = os.environ["COMMENT_MARKER"]
status = os.environ.get("STATUS", "unknown")
summary = os.environ.get("SUMMARY_BODY", "No summary was generated.")
artifact_line = os.environ.get("ARTIFACT_LINE", "Artifact upload disabled or unavailable.")
max_comment_chars = int(os.environ.get("AI_UI_MAX_PR_COMMENT_CHARS", "60000"))
truncation_notice = (
    "\n\n_Full summary truncated to fit the PR comment limit. "
    "See the uploaded artifact for the complete report._"
)

prefix = "\n".join(
    [
        comment_marker,
        "## iOS AI UI Check",
        "",
        f"Status: `{status}`",
        "",
        f"Artifact: {artifact_line}",
        "",
    ]
)

body = prefix + summary
if len(body) > max_comment_chars:
    available_summary_chars = max_comment_chars - len(prefix) - len(truncation_notice)
    if available_summary_chars < 0:
        available_summary_chars = 0
    truncated_summary = summary[:available_summary_chars].rstrip()
    body = prefix + truncated_summary + truncation_notice

with open(payload_path, "w", encoding="utf-8") as handle:
    json.dump({"body": body}, handle)
PY

curl -sS \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  "${GITHUB_API_URL:-https://api.github.com}/repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments?per_page=100" \
  > "${COMMENTS_PATH}"

EXISTING_COMMENT_ID="$(
  COMMENT_MARKER="${COMMENT_MARKER}" \
  python3 - "${COMMENTS_PATH}" <<'PY'
import json
import os
import sys

comment_marker = os.environ["COMMENT_MARKER"]

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    payload = json.load(handle)

for comment in reversed(payload):
    body = comment.get("body", "")
    if comment_marker in body:
        print(comment["id"])
        break
PY
)"

comment_endpoint="${GITHUB_API_URL:-https://api.github.com}/repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments"
comment_method="POST"
if [[ -n "${EXISTING_COMMENT_ID}" ]]; then
  comment_endpoint="${GITHUB_API_URL:-https://api.github.com}/repos/${GITHUB_REPOSITORY}/issues/comments/${EXISTING_COMMENT_ID}"
  comment_method="PATCH"
fi

curl -sS \
  -X "${comment_method}" \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" \
  "${comment_endpoint}" \
  --data @"${PAYLOAD_PATH}" >/dev/null
