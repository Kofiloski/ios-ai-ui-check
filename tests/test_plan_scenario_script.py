from __future__ import annotations

import os
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "plan-scenario.sh"


class PlanScenarioScriptTests(unittest.TestCase):
    def run_plan_script(self, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        merged_env = os.environ.copy()
        merged_env.update(env)
        return subprocess.run(
            ["bash", str(SCRIPT_PATH)],
            cwd=REPO_ROOT,
            env=merged_env,
            check=True,
            capture_output=True,
            text=True,
        )

    def test_invalid_provided_scenario_writes_failure_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts_dir = root / "artifacts"
            scenario_path = root / "provided.json"
            github_output = root / "github-output.txt"

            scenario_path.write_text(
                '{"name":"Invalid provided scenario","steps":[{"action":"tap","value":"unsupported"}]}\n',
                encoding="utf-8",
            )

            self.run_plan_script(
                {
                    "ACTION_ROOT": str(REPO_ROOT),
                    "ARTIFACTS_DIR": str(artifacts_dir),
                    "PROVIDED_SCENARIO_PATH": str(scenario_path),
                    "RUNNER_SCRIPT": str(root / "missing-runner.sh"),
                    "GITHUB_OUTPUT": str(github_output),
                }
            )

            summary = (artifacts_dir / "summary.md").read_text(encoding="utf-8")
            outputs = github_output.read_text(encoding="utf-8")

            self.assertIn("Result: failed", summary)
            self.assertIn("Provided scenario JSON did not match the scenario contract.", summary)
            self.assertIn("status=failed", outputs)
            self.assertIn("summary-path=", outputs)

    def test_release_input_failure_stops_before_planner_and_has_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            output = root / "outputs"
            marker = root / "planner-ran"
            self.run_plan_script({
                "ACTION_ROOT": str(REPO_ROOT), "ARTIFACTS_DIR": str(artifacts),
                "BASE_REF": "missing-release-ref", "HEAD_REF": "HEAD",
                "PLANNER_COMMAND": f"touch {marker}", "GITHUB_OUTPUT": str(output),
            })
            self.assertFalse(marker.exists())
            self.assertIn("status=failed", output.read_text())
            self.assertIn("Change comparison failed", (artifacts / "summary.md").read_text())
            self.assertIn("unavailable", (artifacts / "planner-validation-error.txt").read_text())

    def test_provided_release_smoke_is_rejected_before_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            for text in ["before", "after"]:
                (root / "source.txt").write_text(text)
                subprocess.run(["git", "-C", str(root), "add", "source.txt"], check=True)
                subprocess.run(["git", "-C", str(root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", text], check=True)
            scenario = root / "smoke.json"
            scenario.write_text(json.dumps({"name": "Smoke", "steps": [{"action": "launch"}, {"action": "screenshot"}]}))
            artifacts = root / "artifacts"
            output = root / "outputs"
            self.run_plan_script({"ACTION_ROOT": str(REPO_ROOT), "ARTIFACTS_DIR": str(artifacts),
                                  "AI_UI_WORKSPACE": str(root), "BASE_REF": "HEAD^", "HEAD_REF": "HEAD",
                                  "PROVIDED_SCENARIO_PATH": str(scenario), "GITHUB_OUTPUT": str(output)})
            self.assertIn("status=failed", output.read_text())
            self.assertIn("insufficient assertions", (artifacts / "summary.md").read_text())
            self.assertIn("Other release changes remain unverified", (artifacts / "summary.md").read_text())

    def test_invalid_event_does_not_fall_back_to_parent_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            event = root / "event.json"
            event.write_text("not JSON")
            artifacts = root / "artifacts"
            outputs = root / "outputs"
            self.run_plan_script({"ACTION_ROOT": str(REPO_ROOT), "ARTIFACTS_DIR": str(artifacts),
                                  "GITHUB_EVENT_PATH": str(event), "GITHUB_OUTPUT": str(outputs)})
            self.assertIn("status=failed", outputs.read_text())
            self.assertIn("Cannot read comparison event", (artifacts / "planner-validation-error.txt").read_text())

    def test_invalid_planner_output_writes_planner_summary_and_validation_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts_dir = root / "artifacts"
            github_output = root / "github-output.txt"
            planner_script = root / "fake-planner.sh"
            planner_script.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
cat > "$AI_UI_SCENARIO_OUTPUT_PATH" <<'EOF'
{"name":"Invalid planned scenario","steps":[{"action":"tap","value":"unsupported"}]}
EOF
""",
                encoding="utf-8",
            )
            planner_script.chmod(0o755)

            self.run_plan_script(
                {
                    "ACTION_ROOT": str(REPO_ROOT),
                    "ARTIFACTS_DIR": str(artifacts_dir),
                    "PLANNER_COMMAND": str(planner_script),
                    "RUNNER_SCRIPT": str(root / "missing-runner.sh"),
                    "PLANNER_GOAL": "Verify a primary flow",
                    "GITHUB_OUTPUT": str(github_output),
                }
            )

            summary = (artifacts_dir / "summary.md").read_text(encoding="utf-8")
            planner_summary = (artifacts_dir / "planner-summary.md").read_text(encoding="utf-8")
            planner_validation_error = (
                artifacts_dir / "planner-validation-error.txt"
            ).read_text(encoding="utf-8")

            self.assertIn("Planner command", planner_summary)
            self.assertIn("Planner Goal", planner_summary)
            self.assertIn("Planner validation error", summary)
            self.assertIn("unsupported fields", planner_validation_error)

    def test_explicit_planner_settings_reach_custom_command_and_request_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            planner_script = root / "planner.sh"
            planner_script.write_text('''#!/bin/bash
set -eu
printf '%s\\n' "$AI_UI_PLANNER_PROVIDER" "$AI_UI_PLANNER_MODEL" "$AI_UI_PLANNER_EFFORT" > "$AI_UI_SCENARIO_OUTPUT_PATH.selection"
printf '%s\\n' '{"name":"Fixture","steps":[{"action":"wait","seconds":0}]}' > "$AI_UI_SCENARIO_OUTPUT_PATH"
''')
            planner_script.chmod(0o755)
            self.run_plan_script({
                "ACTION_ROOT": str(REPO_ROOT), "ARTIFACTS_DIR": str(artifacts),
                "PLANNER_COMMAND": str(planner_script), "RUNNER_SCRIPT": str(root / "missing-runner"),
                "GITHUB_OUTPUT": str(root / "outputs"),
                "PLANNER_PROVIDER": "anthropic", "PLANNER_MODEL": "claude-sonnet-4-6", "PLANNER_EFFORT": "high",
                "AI_UI_PLANNER_PROVIDER": "old-provider", "AI_UI_PLANNER_MODEL": "old-model", "AI_UI_PLANNER_EFFORT": "low",
            })
            self.assertEqual((artifacts / "scenario.json.selection").read_text().splitlines(), ["anthropic", "claude-sonnet-4-6", "high"])
            self.assertIn("status=passed", (root / "outputs").read_text())
            request = (artifacts / "planner-request.md").read_text()
            self.assertIn("Requested provider: anthropic", request)
            self.assertIn("Requested model: claude-sonnet-4-6", request)
            self.assertIn("Requested effort: high", request)


if __name__ == "__main__":
    unittest.main()
