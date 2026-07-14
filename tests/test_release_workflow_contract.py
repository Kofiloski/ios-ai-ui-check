from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "release.yml"


class ReleaseWorkflowContractTests(unittest.TestCase):
    def test_release_runs_serially_from_default_branch(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        self.assertIn("group: release", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("DEFAULT_BRANCH: ${{ github.event.repository.default_branch }}", workflow)
        self.assertIn('"${CURRENT_REF}" != "refs/heads/${DEFAULT_BRANCH}"', workflow)

    def test_release_is_resumable_but_rejects_conflicting_exact_tag(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        self.assertIn("already points to the release commit; continuing", workflow)
        self.assertIn("already exists on a different commit", workflow)
        self.assertIn('gh release view "${VERSION_TAG}"', workflow)
        self.assertLess(
            workflow.index("- name: Create GitHub release"),
            workflow.index("- name: Update moving major tag"),
        )


if __name__ == "__main__":
    unittest.main()
