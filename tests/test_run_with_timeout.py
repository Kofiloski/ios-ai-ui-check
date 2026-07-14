from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run-with-timeout.py"
PLAN_SCRIPT_PATH = REPO_ROOT / "scripts" / "plan-scenario.sh"
RUN_CHECK_SCRIPT_PATH = REPO_ROOT / "scripts" / "run-check.sh"


class RunWithTimeoutTests(unittest.TestCase):
    def test_returns_the_command_exit_code(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--timeout",
                "2",
                "--",
                "/bin/bash",
                "-c",
                "exit 7",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 7)

    def test_maps_signal_termination_to_conventional_shell_exit_code(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--timeout",
                "2",
                "--",
                "/bin/bash",
                "-c",
                "kill -KILL $$",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 128 + signal.SIGKILL)

    def test_timeout_terminates_descendants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "descendant-finished"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--timeout",
                    "0.1",
                    "--label",
                    "Test command",
                    "--",
                    "/bin/bash",
                    "-c",
                    f"(sleep 0.5; touch {marker!s}) & wait",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            time.sleep(0.6)

            self.assertEqual(completed.returncode, 124)
            self.assertIn("Test command timed out", completed.stderr)
            self.assertFalse(marker.exists())

    def test_timeout_kills_descendant_after_group_leader_exits_on_sigterm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "ignored-term-descendant-finished"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--timeout",
                    "0.1",
                    "--termination-grace",
                    "0.1",
                    "--label",
                    "Stubborn descendant",
                    "--",
                    "/bin/bash",
                    "-c",
                    (
                        "trap 'exit 0' TERM; "
                        f"(trap '' TERM; sleep 0.5; touch {marker!s}) & "
                        "while true; do sleep 1; done"
                    ),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
            time.sleep(0.6)

            self.assertEqual(completed.returncode, 124)
            self.assertIn("Stubborn descendant timed out", completed.stderr)
            self.assertFalse(marker.exists())

    def test_signal_during_timeout_cleanup_does_not_abort_group_escalation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "late-signal-descendant-finished"
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--timeout",
                    "0.1",
                    "--termination-grace",
                    "0.5",
                    "--label",
                    "Late-signal command",
                    "--",
                    "/bin/bash",
                    "-c",
                    (
                        "trap 'exit 0' TERM; "
                        f"(trap '' TERM; sleep 1; touch {marker!s}) & "
                        "while true; do sleep 1; done"
                    ),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            time.sleep(0.25)
            process.send_signal(signal.SIGTERM)
            _, stderr = process.communicate(timeout=3)
            time.sleep(1.1)

            self.assertEqual(process.returncode, 124)
            self.assertIn("Late-signal command timed out", stderr)
            self.assertFalse(marker.exists())

    def test_planner_command_uses_the_bounded_process_group_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts_dir = root / "artifacts"
            github_output = root / "github-output.txt"
            completed = subprocess.run(
                ["/bin/bash", str(PLAN_SCRIPT_PATH)],
                cwd=REPO_ROOT,
                env={
                    "PATH": os.environ["PATH"],
                    "ACTION_ROOT": str(REPO_ROOT),
                    "ARTIFACTS_DIR": str(artifacts_dir),
                    "GITHUB_OUTPUT": str(github_output),
                    "MAX_DURATION_SECONDS": "1",
                    "PLANNER_COMMAND": "sleep 10",
                    "RUNNER_SCRIPT": str(root / "missing-runner.sh"),
                },
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertEqual(completed.returncode, 0)
            self.assertIn(
                "Planner command timed out after 1 seconds.",
                (artifacts_dir / "summary.md").read_text(encoding="utf-8"),
            )
            self.assertIn("status=failed", github_output.read_text(encoding="utf-8"))

    def test_run_check_reports_timeout_and_overrides_success_looking_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            action_root = root / "action"
            action_scripts = action_root / "scripts"
            action_scripts.mkdir(parents=True)
            shutil.copy2(SCRIPT_PATH, action_scripts / SCRIPT_PATH.name)

            boot_script = action_scripts / "boot-simulator.sh"
            boot_script.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$(dirname "$1")"
cat > "$1" <<'EOF'
export AI_UI_SIMULATOR_UDID='FAKE-UDID'
export AI_UI_SIMULATOR_DEVICE_NAME='Fake iPhone'
export AI_UI_SIMULATOR_RUNTIME_ID='com.apple.CoreSimulator.SimRuntime.iOS-26-2'
export AI_UI_SIMULATOR_RUNTIME_NAME='iOS 26.2'
EOF
""",
                encoding="utf-8",
            )
            boot_script.chmod(0o755)

            runner_script = root / "runner.sh"
            runner_script.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
cat > "$AI_UI_ARTIFACTS_DIR/summary.md" <<'EOF'
## Runner Summary

Result: passed
EOF
sleep 10
""",
                encoding="utf-8",
            )
            runner_script.chmod(0o755)

            artifacts_dir = root / "artifacts"
            scenario_path = root / "scenario.json"
            scenario_path.write_text('{}\n', encoding="utf-8")
            github_output = root / "github-output.txt"
            completed = subprocess.run(
                ["/bin/bash", str(RUN_CHECK_SCRIPT_PATH)],
                cwd=REPO_ROOT,
                env={
                    **os.environ,
                    "ACTION_ROOT": str(action_root),
                    "RUNNER_SCRIPT": str(runner_script),
                    "ARTIFACTS_DIR": str(artifacts_dir),
                    "SCENARIO_PATH": str(scenario_path),
                    "SIMULATOR_NAME": "Fake iPhone",
                    "SIMULATOR_RUNTIME": "26.2",
                    "RECORD_VIDEO": "false",
                    "MAX_DURATION_SECONDS": "1",
                    "GITHUB_OUTPUT": str(github_output),
                },
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = (artifacts_dir / "summary.md").read_text(encoding="utf-8")
            outputs = github_output.read_text(encoding="utf-8")
            self.assertIn("Result: failed", summary)
            self.assertNotIn("Result: passed", summary)
            self.assertIn("Runner timed out after 1 seconds.", summary)
            self.assertIn("failure-note=Runner timed out after 1 seconds.", outputs)

    def test_run_check_omits_video_when_recorder_does_not_finalize(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            action_root = root / "action"
            action_scripts = action_root / "scripts"
            action_scripts.mkdir(parents=True)
            shutil.copy2(SCRIPT_PATH, action_scripts / SCRIPT_PATH.name)

            boot_script = action_scripts / "boot-simulator.sh"
            boot_script.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$(dirname "$1")"
cat > "$1" <<'EOF'
export AI_UI_SIMULATOR_UDID='FAKE-UDID'
export AI_UI_SIMULATOR_DEVICE_NAME='Fake iPhone'
export AI_UI_SIMULATOR_RUNTIME_ID='com.apple.CoreSimulator.SimRuntime.iOS-26-2'
export AI_UI_SIMULATOR_RUNTIME_NAME='iOS 26.2'
EOF
""",
                encoding="utf-8",
            )
            boot_script.chmod(0o755)

            record_script = action_scripts / "record-video.sh"
            record_script.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "start" ]]; then
  mkdir -p "$(dirname "$4")"
  printf 'unfinalized' > "$4"
  printf '123\n' > "$2"
  exit 0
fi
exit 1
""",
                encoding="utf-8",
            )
            record_script.chmod(0o755)

            runner_script = root / "runner.sh"
            runner_script.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
cat > "$AI_UI_ARTIFACTS_DIR/summary.md" <<'EOF'
## Runner Summary

Result: passed
EOF
""",
                encoding="utf-8",
            )
            runner_script.chmod(0o755)

            artifacts_dir = root / "artifacts"
            scenario_path = root / "scenario.json"
            scenario_path.write_text('{}\n', encoding="utf-8")
            github_output = root / "github-output.txt"
            completed = subprocess.run(
                ["/bin/bash", str(RUN_CHECK_SCRIPT_PATH)],
                cwd=REPO_ROOT,
                env={
                    **os.environ,
                    "ACTION_ROOT": str(action_root),
                    "RUNNER_SCRIPT": str(runner_script),
                    "ARTIFACTS_DIR": str(artifacts_dir),
                    "SCENARIO_PATH": str(scenario_path),
                    "SIMULATOR_NAME": "Fake iPhone",
                    "SIMULATOR_RUNTIME": "26.2",
                    "RECORD_VIDEO": "true",
                    "MAX_DURATION_SECONDS": "2",
                    "GITHUB_OUTPUT": str(github_output),
                },
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = (artifacts_dir / "summary.md").read_text(encoding="utf-8")
            outputs = github_output.read_text(encoding="utf-8")
            self.assertIn("Video recording did not finalize successfully", summary)
            self.assertIn("video-path=\n", outputs)
            self.assertFalse((artifacts_dir / "run.mp4").exists())

    def test_run_check_does_not_stop_video_before_recording_starts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            action_scripts = root / "action" / "scripts"
            action_scripts.mkdir(parents=True)
            recorder_invocation = root / "recorder-invoked"
            record_script = action_scripts / "record-video.sh"
            record_script.write_text(
                f"#!/usr/bin/env bash\ntouch {recorder_invocation!s}\n",
                encoding="utf-8",
            )
            record_script.chmod(0o755)

            github_output = root / "github-output.txt"
            artifacts_dir = root / "artifacts"
            completed = subprocess.run(
                ["/bin/bash", str(RUN_CHECK_SCRIPT_PATH)],
                cwd=REPO_ROOT,
                env={
                    **os.environ,
                    "ACTION_ROOT": str(root / "action"),
                    "RUNNER_SCRIPT": str(root / "runner.sh"),
                    "ARTIFACTS_DIR": str(artifacts_dir),
                    "SCENARIO_PATH": str(root / "scenario.json"),
                    "SIMULATOR_NAME": "Fake iPhone",
                    "SIMULATOR_RUNTIME": "26.2",
                    "RECORD_VIDEO": "true",
                    "MAX_DURATION_SECONDS": "0",
                    "GITHUB_OUTPUT": str(github_output),
                },
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse(recorder_invocation.exists())
            summary = (artifacts_dir / "summary.md").read_text(encoding="utf-8")
            self.assertNotIn("Video note:", summary)

    def test_run_check_continues_when_video_recording_fails_to_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            action_root = root / "action"
            action_scripts = action_root / "scripts"
            action_scripts.mkdir(parents=True)
            shutil.copy2(SCRIPT_PATH, action_scripts / SCRIPT_PATH.name)

            boot_script = action_scripts / "boot-simulator.sh"
            boot_script.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$(dirname "$1")"
cat > "$1" <<'EOF'
export AI_UI_SIMULATOR_UDID='FAKE-UDID'
export AI_UI_SIMULATOR_DEVICE_NAME='Fake iPhone'
export AI_UI_SIMULATOR_RUNTIME_ID='com.apple.CoreSimulator.SimRuntime.iOS-26-2'
export AI_UI_SIMULATOR_RUNTIME_NAME='iOS 26.2'
EOF
""",
                encoding="utf-8",
            )
            boot_script.chmod(0o755)

            record_script = action_scripts / "record-video.sh"
            record_script.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "start" ]]; then
  mkdir -p "$4"
  printf 'stale-pid\n' > "$2"
  exit 1
fi
exit 0
""",
                encoding="utf-8",
            )
            record_script.chmod(0o755)

            runner_marker = root / "runner-finished"
            runner_script = root / "runner.sh"
            runner_script.write_text(
                f"""#!/usr/bin/env bash
set -euo pipefail
touch {runner_marker!s}
cat > "$AI_UI_ARTIFACTS_DIR/summary.md" <<'EOF'
## Runner Summary

Result: passed
EOF
""",
                encoding="utf-8",
            )
            runner_script.chmod(0o755)

            artifacts_dir = root / "artifacts"
            scenario_path = root / "scenario.json"
            scenario_path.write_text('{}\n', encoding="utf-8")
            github_output = root / "github-output.txt"
            completed = subprocess.run(
                ["/bin/bash", str(RUN_CHECK_SCRIPT_PATH)],
                cwd=REPO_ROOT,
                env={
                    **os.environ,
                    "ACTION_ROOT": str(action_root),
                    "RUNNER_SCRIPT": str(runner_script),
                    "ARTIFACTS_DIR": str(artifacts_dir),
                    "SCENARIO_PATH": str(scenario_path),
                    "SIMULATOR_NAME": "Fake iPhone",
                    "SIMULATOR_RUNTIME": "26.2",
                    "RECORD_VIDEO": "true",
                    "MAX_DURATION_SECONDS": "2",
                    "GITHUB_OUTPUT": str(github_output),
                },
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(runner_marker.exists())
            summary = (artifacts_dir / "summary.md").read_text(encoding="utf-8")
            outputs = github_output.read_text(encoding="utf-8")
            self.assertIn("Result: passed", summary)
            self.assertIn("Video recording failed to start", summary)
            self.assertIn("status=passed\n", outputs)
            self.assertIn("video-path=\n", outputs)
            self.assertTrue((artifacts_dir / "run.mp4").is_dir())
            self.assertFalse((artifacts_dir / "record-video.pid").exists())


if __name__ == "__main__":
    unittest.main()
