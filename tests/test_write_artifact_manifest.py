from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "write-artifact-manifest.py"
SPEC = importlib.util.spec_from_file_location("write_artifact_manifest", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
write_artifact_manifest = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = write_artifact_manifest
SPEC.loader.exec_module(write_artifact_manifest)


class WriteArtifactManifestTests(unittest.TestCase):
    def test_build_manifest_records_primary_and_extra_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts_dir = Path(tmp) / "artifacts"
            inspect_dir = artifacts_dir / "inspect"
            xcresult_dir = artifacts_dir / "TestRun.xcresult"
            inspect_dir.mkdir(parents=True)
            xcresult_dir.mkdir(parents=True)

            summary_path = artifacts_dir / "summary.md"
            summary_path.write_text("summary\n", encoding="utf-8")
            screenshot_path = inspect_dir / "before-planning-screenshot.png"
            screenshot_path.write_bytes(b"png")
            (xcresult_dir / "Info.plist").write_text("plist\n", encoding="utf-8")

            manifest = write_artifact_manifest.build_manifest(
                artifacts_dir=artifacts_dir,
                output_path=artifacts_dir / "manifest.json",
                status="failed",
                resolved_source="ai",
                failure_note="Planner failed",
                known_paths={
                    "summary_path": summary_path,
                    "scenario_path": None,
                    "video_path": None,
                    "failure_screenshot_path": None,
                    "before_planning_ui_tree_path": None,
                    "before_planning_screenshot_path": screenshot_path,
                    "planner_note_path": None,
                    "planner_request_path": None,
                    "planner_response_path": None,
                    "planner_validation_error_path": None,
                    "planner_summary_path": None,
                },
            )

            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["resolved_source"], "ai")
            self.assertEqual(manifest["primary_artifacts"]["summary"], "summary.md")
            self.assertEqual(
                manifest["primary_artifacts"]["before-planning-screenshot"],
                "inspect/before-planning-screenshot.png",
            )
            extra_paths = {
                entry["relative_path"]
                for entry in manifest["artifacts"]
                if str(entry["key"]).startswith("extra:")
            }
            self.assertIn("TestRun.xcresult", extra_paths)

    def test_main_writes_manifest_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts_dir = Path(tmp) / "artifacts"
            artifacts_dir.mkdir(parents=True)
            (artifacts_dir / "summary.md").write_text("summary\n", encoding="utf-8")
            output_path = artifacts_dir / "manifest.json"

            result = write_artifact_manifest.build_manifest(
                artifacts_dir=artifacts_dir,
                output_path=output_path,
                status="passed",
                resolved_source="provided",
                failure_note="",
                known_paths={
                    "summary_path": artifacts_dir / "summary.md",
                    "scenario_path": None,
                    "video_path": None,
                    "failure_screenshot_path": None,
                    "before_planning_ui_tree_path": None,
                    "before_planning_screenshot_path": None,
                    "planner_note_path": None,
                    "planner_request_path": None,
                    "planner_response_path": None,
                    "planner_validation_error_path": None,
                    "planner_summary_path": None,
                },
            )

            output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            payload = json.loads(output_path.read_text(encoding="utf-8"))

            self.assertEqual(payload["tool"], "ios-ai-ui-check")
            self.assertEqual(payload["primary_artifacts"]["summary"], "summary.md")


if __name__ == "__main__":
    unittest.main()
