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

if [[ -z "${GITHUB_REPOSITORY:-}" ]]; then
  echo "GITHUB_REPOSITORY is not available. Skipping PR comment."
  exit 0
fi

PR_METADATA="$(python3 - "${GITHUB_EVENT_PATH}" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    payload = json.load(handle)

pull_request = payload.get("pull_request") or {}
number = pull_request.get("number")
if isinstance(number, int) and number > 0:
    head_repo = (pull_request.get("head") or {}).get("repo") or {}
    base_repo = (pull_request.get("base") or {}).get("repo") or {}
    head_name = str(head_repo.get("full_name") or "")
    base_name = str(base_repo.get("full_name") or "")
    author = str((pull_request.get("user") or {}).get("login") or "")
    is_fork = bool(head_name) and bool(base_name) and head_name != base_name
    restricted_token = is_fork or author.casefold() == "dependabot[bot]"
    print(f"{number}\t{'true' if restricted_token else 'false'}")
PY
)"

IFS=$'\t' read -r PR_NUMBER RESTRICTED_PR_TOKEN <<< "${PR_METADATA}"

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
HEADERS_PATH="$(mktemp)"
trap 'rm -f "${PAYLOAD_PATH}" "${COMMENTS_PATH}" "${HEADERS_PATH}"' EXIT

http_status_from_headers() {
  awk 'toupper($1) ~ /^HTTP\// { status = $2 } END { print status }' "$1"
}

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

EXPECTED_COMMENT_AUTHOR_LOGIN="${AI_UI_COMMENT_AUTHOR_LOGIN:-github-actions[bot]}"
MAX_COMMENT_PAGES="${AI_UI_MAX_COMMENT_PAGES:-100}"
if [[ "${#EXPECTED_COMMENT_AUTHOR_LOGIN}" -gt 100 || ! "${EXPECTED_COMMENT_AUTHOR_LOGIN}" =~ ^[A-Za-z0-9_][A-Za-z0-9_-]*(\[bot\])?$ ]]; then
  echo "AI_UI_COMMENT_AUTHOR_LOGIN must be a valid GitHub user or bot login" >&2
  exit 1
fi

if [[ ! "${MAX_COMMENT_PAGES}" =~ ^[1-9][0-9]*$ ]]; then
  echo "AI_UI_MAX_COMMENT_PAGES must be a positive integer" >&2
  exit 1
fi

api_url="${GITHUB_API_URL:-https://api.github.com}"
comments_endpoint="${api_url}/repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments"
EXISTING_COMMENT_ID=""
page=1

while [[ "${page}" -le "${MAX_COMMENT_PAGES}" ]]; do
  : > "${HEADERS_PATH}"
  if ! curl -fsS --retry 2 --retry-delay 1 \
      -D "${HEADERS_PATH}" \
      -H "Authorization: Bearer ${GITHUB_TOKEN}" \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      "${comments_endpoint}?per_page=100&page=${page}" \
      > "${COMMENTS_PATH}"; then
    HTTP_STATUS="$(http_status_from_headers "${HEADERS_PATH}")"
    if [[ "${RESTRICTED_PR_TOKEN:-false}" == "true" && "${AI_UI_DEFAULT_GITHUB_TOKEN:-false}" == "true" && "${HTTP_STATUS}" == "403" ]]; then
      echo "GitHub denied PR comment access to its default token for this fork or Dependabot pull request. Skipping PR comment."
      exit 0
    fi
    echo "GitHub PR comment lookup failed." >&2
    exit 1
  fi

  PAGE_METADATA="$(
    COMMENT_MARKER="${COMMENT_MARKER}" \
    EXPECTED_COMMENT_AUTHOR_LOGIN="${EXPECTED_COMMENT_AUTHOR_LOGIN}" \
    python3 - "${COMMENTS_PATH}" <<'PY'
import json
import os
import sys

comment_marker = os.environ["COMMENT_MARKER"]
expected_author_login = os.environ["EXPECTED_COMMENT_AUTHOR_LOGIN"]

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    payload = json.load(handle)

if not isinstance(payload, list):
    raise SystemExit("GitHub issue-comments response was not a JSON array")

existing_comment_id = ""
for comment in reversed(payload):
    body = comment.get("body") or ""
    author = comment.get("user") or {}
    if (
        body.startswith(comment_marker + "\n")
        and str(author.get("login") or "").casefold() == expected_author_login.casefold()
    ):
        existing_comment_id = str(comment["id"])
        break

print(f"{len(payload)}\t{existing_comment_id}")
PY
  )"

  IFS=$'\t' read -r PAGE_COUNT PAGE_COMMENT_ID <<< "${PAGE_METADATA}"
  if [[ -n "${PAGE_COMMENT_ID:-}" ]]; then
    EXISTING_COMMENT_ID="${PAGE_COMMENT_ID}"
  fi

  if [[ "${PAGE_COUNT}" -lt 100 ]]; then
    break
  fi

  page=$((page + 1))
done

if [[ "${page}" -gt "${MAX_COMMENT_PAGES}" && "${PAGE_COUNT:-100}" -eq 100 ]]; then
  echo "PR comment lookup exceeded AI_UI_MAX_COMMENT_PAGES=${MAX_COMMENT_PAGES}" >&2
  exit 1
fi

comment_endpoint="${comments_endpoint}"
comment_method="POST"
if [[ -n "${EXISTING_COMMENT_ID}" ]]; then
  comment_endpoint="${api_url}/repos/${GITHUB_REPOSITORY}/issues/comments/${EXISTING_COMMENT_ID}"
  comment_method="PATCH"
fi

: > "${HEADERS_PATH}"
if ! curl -fsS --retry 2 --retry-delay 1 \
    -D "${HEADERS_PATH}" \
    -X "${comment_method}" \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    -H "Content-Type: application/json" \
    "${comment_endpoint}" \
    --data @"${PAYLOAD_PATH}" >/dev/null; then
  HTTP_STATUS="$(http_status_from_headers "${HEADERS_PATH}")"
  if [[ "${RESTRICTED_PR_TOKEN:-false}" == "true" && "${AI_UI_DEFAULT_GITHUB_TOKEN:-false}" == "true" && "${HTTP_STATUS}" == "403" ]]; then
    echo "GitHub denied PR comment writes to its default token for this fork or Dependabot pull request. Skipping PR comment."
    exit 0
  fi
  echo "GitHub PR comment update failed." >&2
  exit 1
fi
