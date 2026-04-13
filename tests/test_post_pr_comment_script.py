from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "post-pr-comment.sh"


class PostPRCommentScriptTests(unittest.TestCase):
    def test_updates_existing_managed_comment_with_rendered_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_curl = root / "curl"
            comments_json = root / "comments.json"
            payload_capture = root / "payload.json"
            method_capture = root / "method.txt"
            endpoint_capture = root / "endpoint.txt"
            event_path = root / "event.json"
            summary_path = root / "summary.md"

            comments_json.write_text(
                json.dumps(
                    [
                        {"id": 10, "body": "unrelated"},
                        {
                            "id": 42,
                            "body": "<!-- ios-ai-ui-check:managed-comment -->\nold comment",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            event_path.write_text(
                json.dumps({"pull_request": {"number": 7}}),
                encoding="utf-8",
            )
            summary_path.write_text(
                "## iOS AI UI Check\n\n- Result: passed\n- Scenario: verify flow\n",
                encoding="utf-8",
            )
            fake_curl.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    set -euo pipefail

                    endpoint=""
                    method="GET"
                    data_arg=""
                    previous=""
                    for arg in "$@"; do
                      if [[ "$previous" == "-X" ]]; then
                        method="$arg"
                      elif [[ "$previous" == "--data" ]]; then
                        data_arg="$arg"
                      fi
                      if [[ "$arg" == http* ]]; then
                        endpoint="$arg"
                      fi
                      previous="$arg"
                    done

                    if [[ "$endpoint" == *"?per_page=100" ]]; then
                      cat "$FAKE_CURL_COMMENTS_JSON"
                      exit 0
                    fi

                    if [[ -n "$data_arg" && "$data_arg" == @* ]]; then
                      cp "${data_arg#@}" "$FAKE_CURL_PAYLOAD_CAPTURE"
                    fi
                    printf '%s' "$method" > "$FAKE_CURL_METHOD_CAPTURE"
                    printf '%s' "$endpoint" > "$FAKE_CURL_ENDPOINT_CAPTURE"
                    """
                ),
                encoding="utf-8",
            )
            fake_curl.chmod(0o755)

            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{root}:{env['PATH']}",
                    "GITHUB_TOKEN": "test-token",
                    "GITHUB_EVENT_PATH": str(event_path),
                    "GITHUB_REPOSITORY": "owner/repo",
                    "SUMMARY_PATH": str(summary_path),
                    "STATUS": "passed",
                    "ARTIFACT_URL": "https://example.com/artifact",
                    "ARTIFACT_NAME": "ios-ai-ui-check",
                    "FAKE_CURL_COMMENTS_JSON": str(comments_json),
                    "FAKE_CURL_PAYLOAD_CAPTURE": str(payload_capture),
                    "FAKE_CURL_METHOD_CAPTURE": str(method_capture),
                    "FAKE_CURL_ENDPOINT_CAPTURE": str(endpoint_capture),
                }
            )

            subprocess.run(
                ["bash", str(SCRIPT_PATH)],
                cwd=REPO_ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(payload_capture.read_text(encoding="utf-8"))
            self.assertEqual(method_capture.read_text(encoding="utf-8"), "PATCH")
            self.assertIn("/issues/comments/42", endpoint_capture.read_text(encoding="utf-8"))
            self.assertIn("<!-- ios-ai-ui-check:managed-comment -->", payload["body"])
            self.assertIn("Status: `passed`", payload["body"])
            self.assertIn("[ios-ai-ui-check](https://example.com/artifact)", payload["body"])
            self.assertIn("- Result: passed", payload["body"])

    def test_truncates_oversized_summary_before_posting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_curl = root / "curl"
            comments_json = root / "comments.json"
            payload_capture = root / "payload.json"
            event_path = root / "event.json"
            summary_path = root / "summary.md"

            comments_json.write_text("[]", encoding="utf-8")
            event_path.write_text(
                json.dumps({"pull_request": {"number": 9}}),
                encoding="utf-8",
            )
            summary_path.write_text("A" * 70000, encoding="utf-8")
            fake_curl.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    set -euo pipefail

                    endpoint=""
                    data_arg=""
                    previous=""
                    for arg in "$@"; do
                      if [[ "$previous" == "--data" ]]; then
                        data_arg="$arg"
                      fi
                      if [[ "$arg" == http* ]]; then
                        endpoint="$arg"
                      fi
                      previous="$arg"
                    done

                    if [[ "$endpoint" == *"?per_page=100" ]]; then
                      cat "$FAKE_CURL_COMMENTS_JSON"
                      exit 0
                    fi

                    if [[ -n "$data_arg" && "$data_arg" == @* ]]; then
                      cp "${data_arg#@}" "$FAKE_CURL_PAYLOAD_CAPTURE"
                    fi
                    """
                ),
                encoding="utf-8",
            )
            fake_curl.chmod(0o755)

            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{root}:{env['PATH']}",
                    "GITHUB_TOKEN": "test-token",
                    "GITHUB_EVENT_PATH": str(event_path),
                    "GITHUB_REPOSITORY": "owner/repo",
                    "SUMMARY_PATH": str(summary_path),
                    "STATUS": "failed",
                    "FAKE_CURL_COMMENTS_JSON": str(comments_json),
                    "FAKE_CURL_PAYLOAD_CAPTURE": str(payload_capture),
                }
            )

            subprocess.run(
                ["bash", str(SCRIPT_PATH)],
                cwd=REPO_ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(payload_capture.read_text(encoding="utf-8"))
            self.assertLessEqual(len(payload["body"]), 60000)
            self.assertIn("Full summary truncated", payload["body"])


if __name__ == "__main__":
    unittest.main()
