from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "refresh-scaffold.py"
SCAFFOLD_SCRIPT_PATH = REPO_ROOT / "scripts" / "scaffold-app-repo.py"
FIXTURE_APP_ROOT = REPO_ROOT / "tests" / "fixtures" / "tiny-fixture-app"
SPEC = importlib.util.spec_from_file_location("refresh_scaffold", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
refresh_scaffold = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = refresh_scaffold
SPEC.loader.exec_module(refresh_scaffold)


class RefreshScaffoldTests(unittest.TestCase):
    def test_build_command_preserves_customizable_files_by_default(self) -> None:
        manifest = {
            "tool": "ios-ai-ui-check",
            "project_path": "SampleApp.xcodeproj",
            "scheme": "SampleApp",
            "app_target": "SampleAppApp",
            "ui_test_target": "SampleAppUITests",
            "scenario_path": ".github/ai-ui/add-recipe-form.json",
            "simulator_name": "iPhone 17 Pro",
            "simulator_runtime": "26.2",
            "workflow_generated": True,
        }

        command = refresh_scaffold.build_command(
            repo_root=Path("/tmp/SampleApp"),
            manifest=manifest,
            dry_run=True,
            refresh_customizable_files=False,
        )

        self.assertIn("--project", command)
        self.assertIn("SampleApp.xcodeproj", command)
        self.assertIn("--scenario-file-name", command)
        self.assertIn("add-recipe-form.json", command)
        self.assertIn("--preserve-customizable-files", command)
        self.assertIn("--dry-run", command)

    def test_build_command_can_refresh_customizable_files(self) -> None:
        manifest = {
            "tool": "ios-ai-ui-check",
            "project_path": "SampleApp.xcodeproj",
            "scheme": "SampleApp",
            "scenario_path": ".github/ai-ui/verify-primary-flow.json",
            "simulator_name": "iPhone 17 Pro",
            "simulator_runtime": "26.2",
            "workflow_generated": False,
            "scenario_template": "/tmp/scenario.json",
            "planner_context_template": "/tmp/planner-context.md",
        }

        command = refresh_scaffold.build_command(
            repo_root=Path("/tmp/SampleApp"),
            manifest=manifest,
            dry_run=False,
            refresh_customizable_files=True,
        )

        self.assertNotIn("--preserve-customizable-files", command)
        self.assertIn("--scenario-template", command)
        self.assertIn("/tmp/scenario.json", command)
        self.assertIn("--planner-context-template", command)
        self.assertIn("/tmp/planner-context.md", command)
        self.assertIn("--skip-workflow", command)

    def test_collect_local_modifications_reports_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "FixtureApp"
            shutil.copytree(FIXTURE_APP_ROOT, repo_root)

            subprocess.run(
                [
                    sys.executable,
                    str(SCAFFOLD_SCRIPT_PATH),
                    "--repo-root",
                    str(repo_root),
                    "--project",
                    "FixtureApp.xcodeproj",
                    "--scheme",
                    "FixtureApp",
                ],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            manifest = json.loads(
                (repo_root / ".github" / "ai-ui" / "scaffold-manifest.json").read_text(encoding="utf-8")
            )
            report = refresh_scaffold.collect_local_modifications(
                repo_root=repo_root,
                manifest=manifest,
            )

            self.assertEqual(report["status"], "available")
            self.assertEqual(report["changes"], [])

            (repo_root / "scripts" / "run-ai-ui-scenario.sh").write_text(
                "# locally modified\n",
                encoding="utf-8",
            )
            (repo_root / ".github" / "ai-ui" / "planner-context.md").write_text(
                "custom planner context\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--repo-root",
                    str(repo_root),
                    "--dry-run",
                ],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertIn(
                "managed modified: scripts/run-ai-ui-scenario.sh (will be overwritten)",
                completed.stdout,
            )
            self.assertIn(
                "customizable modified: .github/ai-ui/planner-context.md (will be preserved)",
                completed.stdout,
            )

    def test_build_check_result_flags_unavailable_hashes(self) -> None:
        report = refresh_scaffold.build_check_result(
            {"status": "unavailable", "changes": []}
        )

        self.assertFalse(report["ok"])
        self.assertEqual(report["reason"], "manifest predates content hashes")

    def test_check_mode_and_json_report_detect_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "FixtureApp"
            shutil.copytree(FIXTURE_APP_ROOT, repo_root)

            subprocess.run(
                [
                    sys.executable,
                    str(SCAFFOLD_SCRIPT_PATH),
                    "--repo-root",
                    str(repo_root),
                    "--project",
                    "FixtureApp.xcodeproj",
                    "--scheme",
                    "FixtureApp",
                ],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            (repo_root / "scripts" / "run-ai-ui-scenario.sh").write_text(
                "# locally modified\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--repo-root",
                    str(repo_root),
                    "--check",
                    "--json",
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 1)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["mode"], "check")
            self.assertFalse(payload["check_result"]["ok"])
            self.assertEqual(payload["scaffold"]["executed"], False)
            self.assertEqual(
                payload["local_modifications"]["changes"][0]["relative_path"],
                "scripts/run-ai-ui-scenario.sh",
            )


if __name__ == "__main__":
    unittest.main()
