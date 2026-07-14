from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = REPO_ROOT / "templates" / "workflow.yml.tpl"
ACTION_PATH = REPO_ROOT / "action.yml"


class WorkflowTemplateContractTests(unittest.TestCase):
    def test_app_checkout_preserves_pr_diff_history(self) -> None:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
        app_checkout = template.split("- name: Checkout app repo", maxsplit=1)[1].split(
            "- name: Checkout ios-ai-ui-check", maxsplit=1
        )[0]

        self.assertIn("fetch-depth: 0", app_checkout)

    def test_dispatch_values_enter_shell_through_step_environment(self) -> None:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
        prewarm_step = template.split(
            "- name: Prewarm simulator and build for testing", maxsplit=1
        )[1].split("- name: Run AI UI action", maxsplit=1)[0]

        self.assertIn("REQUESTED_SIMULATOR_NAME:", prewarm_step)
        self.assertIn("REQUESTED_SIMULATOR_RUNTIME:", prewarm_step)
        run_script = prewarm_step.split("run: |", maxsplit=1)[1]
        self.assertNotIn("${{ inputs.simulator_name", run_script)
        self.assertNotIn("${{ inputs.simulator_runtime", run_script)

    def test_simulator_environment_uses_github_environment_file_format(self) -> None:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")

        self.assertIn('handle.write(f"{key}<<{delimiter}\\n")', template)
        self.assertNotIn(
            'cat "$RUNNER_TEMP/ios-ai-ui-simulator.env" >> "$GITHUB_ENV"',
            template,
        )

    def test_generated_and_direct_actions_forward_comment_token(self) -> None:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
        action = ACTION_PATH.read_text(encoding="utf-8")

        self.assertNotIn("github-token: ${{ github.token }}", template)
        self.assertIn("github-token:", action)
        self.assertIn("comment-author-login:", action)
        self.assertIn(
            "GITHUB_TOKEN: ${{ inputs.github-token || env.GITHUB_TOKEN || github.token }}",
            action,
        )
        self.assertIn(
            "AI_UI_COMMENT_AUTHOR_LOGIN: ${{ inputs.comment-author-login || env.AI_UI_COMMENT_AUTHOR_LOGIN || 'github-actions[bot]' }}",
            action,
        )


if __name__ == "__main__":
    unittest.main()
