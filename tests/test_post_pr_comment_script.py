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
                            "user": {"login": "github-actions[bot]"},
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

                    if [[ "$endpoint" == *"?per_page=100&page=1" ]]; then
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

                    if [[ "$endpoint" == *"?per_page=100&page=1" ]]; then
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

    def test_paginates_and_ignores_spoofed_marker_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_curl = root / "curl"
            first_page = root / "comments-page-1.json"
            second_page = root / "comments-page-2.json"
            payload_capture = root / "payload.json"
            method_capture = root / "method.txt"
            endpoint_capture = root / "endpoint.txt"
            event_path = root / "event.json"

            page_one_comments = [
                {"id": index, "body": "unrelated", "user": {"login": "someone"}}
                for index in range(1, 100)
            ]
            page_one_comments.append(
                {
                    "id": 100,
                    "body": "<!-- ios-ai-ui-check:managed-comment -->\nspoofed",
                    "user": {"login": "untrusted-user"},
                }
            )
            first_page.write_text(json.dumps(page_one_comments), encoding="utf-8")
            second_page.write_text(
                json.dumps(
                    [
                        {
                            "id": 142,
                            "body": "<!-- ios-ai-ui-check:managed-comment -->\nmanaged",
                            "user": {"login": "release_bot[bot]"},
                        }
                    ]
                ),
                encoding="utf-8",
            )
            event_path.write_text(
                json.dumps({"pull_request": {"number": 11}}),
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

                    if [[ "$endpoint" == *"?per_page=100&page=1" ]]; then
                      cat "$FAKE_CURL_FIRST_PAGE"
                      exit 0
                    fi
                    if [[ "$endpoint" == *"?per_page=100&page=2" ]]; then
                      cat "$FAKE_CURL_SECOND_PAGE"
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
                    "STATUS": "passed",
                    "AI_UI_COMMENT_AUTHOR_LOGIN": "Release_Bot[bot]",
                    "FAKE_CURL_FIRST_PAGE": str(first_page),
                    "FAKE_CURL_SECOND_PAGE": str(second_page),
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

            self.assertTrue(payload_capture.exists())
            self.assertEqual(method_capture.read_text(encoding="utf-8"), "PATCH")
            self.assertIn(
                "/issues/comments/142",
                endpoint_capture.read_text(encoding="utf-8"),
            )

    def test_rejects_invalid_expected_comment_author_login(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            event_path = root / "event.json"
            event_path.write_text(
                json.dumps({"pull_request": {"number": 12}}),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.update(
                {
                    "GITHUB_TOKEN": "test-token",
                    "GITHUB_EVENT_PATH": str(event_path),
                    "GITHUB_REPOSITORY": "owner/repo",
                    "AI_UI_COMMENT_AUTHOR_LOGIN": "bad/login",
                }
            )

            result = subprocess.run(
                ["bash", str(SCRIPT_PATH)],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("valid GitHub user or bot login", result.stderr)

    def test_fails_when_github_comment_api_returns_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_curl = root / "curl"
            event_path = root / "event.json"
            event_path.write_text(
                json.dumps({"pull_request": {"number": 13}}),
                encoding="utf-8",
            )
            fake_curl.write_text(
                "#!/usr/bin/env bash\nexit 22\n",
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
                }
            )

            result = subprocess.run(
                ["bash", str(SCRIPT_PATH)],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
