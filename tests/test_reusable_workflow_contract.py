from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "run.yml"


class ReusableWorkflowContractTests(unittest.TestCase):
    def test_workflow_forwards_action_outputs_and_generic_planner_secret(self) -> None:
        workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

        self.assertIn("planner-api-key-env-name:", workflow_text)
        self.assertIn("planner-api-key:", workflow_text)
        self.assertIn("id: run_action", workflow_text)
        self.assertIn("artifact-manifest-path:", workflow_text)
        self.assertIn("resolved-source:", workflow_text)
        self.assertIn("failure-note:", workflow_text)
        self.assertIn("upload-artifacts:", workflow_text)
        self.assertIn("record-video:", workflow_text)
        self.assertIn("max-duration-seconds:", workflow_text)
        self.assertIn("printf '%s=%s\\n' \"${PLANNER_API_KEY_ENV_NAME}\" \"${PLANNER_API_KEY}\" >> \"$GITHUB_ENV\"", workflow_text)


if __name__ == "__main__":
    unittest.main()
