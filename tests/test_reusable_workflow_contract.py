from __future__ import annotations

import unittest
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "run.yml"


class ReusableWorkflowContractTests(unittest.TestCase):
    def test_workflow_forwards_action_outputs_and_generic_planner_secret(self) -> None:
        workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

        self.assertIn("planner-api-key-env-name:", workflow_text)
        self.assertIn('dict.fromkeys((name, "AI_UI_PLANNER_API_KEY"))', workflow_text)
        self.assertIn("planner-api-key:", workflow_text)
        self.assertIn("id: run_action", workflow_text)
        self.assertIn("artifact-manifest-path:", workflow_text)
        self.assertIn("resolved-source:", workflow_text)
        self.assertIn("failure-note:", workflow_text)
        self.assertIn("upload-artifacts:", workflow_text)
        self.assertIn("record-video:", workflow_text)
        self.assertIn("max-duration-seconds:", workflow_text)
        for name in ("base-ref", "head-ref", "release-notes-path", "planner-provider", "planner-model", "planner-effort", "planner-base-url"):
            self.assertIn(f"{name}: ${{{{ inputs.{name} }}}}", workflow_text)
        self.assertIn("github-token: ${{ secrets['github-token'] }}", workflow_text)
        self.assertIn("comment-author-login: ${{ inputs.comment-author-login }}", workflow_text)

        action_text = (REPO_ROOT / "action.yml").read_text(encoding="utf-8")
        self.assertIn(
            "GITHUB_TOKEN: ${{ inputs.github-token || env.GITHUB_TOKEN || github.token }}",
            action_text,
        )
        self.assertIn("AI_UI_DEFAULT_GITHUB_TOKEN:", action_text)
        self.assertIn("inputs.github-token == github.token", action_text)
        self.assertIn("env.GITHUB_TOKEN == github.token", action_text)
        self.assertIn("scripts/write-job-summary.py", action_text)

    def test_checks_out_caller_at_workspace_root_with_history(self) -> None:
        workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

        caller_checkout = workflow_text.split(
            "- name: Checkout caller repository", maxsplit=1
        )[1].split("- name: Checkout action repository", maxsplit=1)[0]
        self.assertIn("fetch-depth: 0", caller_checkout)
        self.assertIn("ref: ${{ inputs.head-ref || github.ref }}", caller_checkout)
        self.assertNotIn("path: repo", caller_checkout)
        self.assertNotIn("format('repo/{0}'", workflow_text)

    def test_checks_out_called_workflow_at_immutable_job_identity(self) -> None:
        workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        action_checkout = workflow_text.split(
            "- name: Checkout action repository", maxsplit=1
        )[1].split("- name: Export planner API key", maxsplit=1)[0]

        self.assertIn("repository: ${{ job.workflow_repository }}", action_checkout)
        self.assertIn("ref: ${{ job.workflow_sha }}", action_checkout)
        self.assertNotIn("github.workflow_ref", workflow_text)
        self.assertNotIn("Resolve action repository and ref", workflow_text)

    def test_validates_and_multiline_exports_planner_secret(self) -> None:
        workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

        self.assertIn("^[A-Za-z_][A-Za-z0-9_]*$", workflow_text)
        self.assertIn("GITHUB_*|RUNNER_*|NODE_OPTIONS", workflow_text)
        self.assertIn('handle.write(f"{name}<<{delimiter}\\n")', workflow_text)
        self.assertNotIn(
            "printf '%s=%s\\n' \"${PLANNER_API_KEY_ENV_NAME}\"",
            workflow_text,
        )

    def test_secret_is_checked_inside_shell_instead_of_step_if(self) -> None:
        workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

        for line in workflow_text.splitlines():
            if line.lstrip().startswith("if:"):
                self.assertNotIn("secrets", line)
        self.assertIn('if [[ -z "${PLANNER_API_KEY}" ]]', workflow_text)

    def test_planner_secret_preserves_legacy_name_and_exports_generic_key(self) -> None:
        workflow = WORKFLOW_PATH.read_text()
        step = workflow.split("- name: Export planner API key", 1)[1]
        script = textwrap.dedent(step.split("python3 - <<'PY'", 1)[1].split("\n          PY", 1)[0])
        for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AI_UI_PLANNER_API_KEY"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / "github-env"
                key = "fixture-line-one\nfixture-line-two"
                subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True,
                               env={**os.environ, "PLANNER_API_KEY_ENV_NAME": name, "PLANNER_API_KEY": key, "GITHUB_ENV": str(target)})
                exported = target.read_text()
                for expected in {name, "AI_UI_PLANNER_API_KEY"}:
                    self.assertEqual(exported.count(expected + "<<"), 1)
                self.assertIn(key, exported)


if __name__ == "__main__":
    unittest.main()
