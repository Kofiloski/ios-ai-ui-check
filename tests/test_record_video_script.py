from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import time
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "record-video.sh"


class RecordVideoScriptTests(unittest.TestCase):
    def test_stop_waits_for_sigint_finalization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_xcrun = root / "xcrun"
            finalized_path = root / "finalized.txt"
            started_path = root / "started.txt"
            pid_path = root / "state" / "record-video.pid"
            video_path = root / "artifacts" / "video.mp4"
            fake_xcrun.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    trap 'sleep 1; printf finalized > "$FAKE_FINALIZED_PATH"; exit 0' INT
                    printf started > "$FAKE_STARTED_PATH"
                    while true; do
                      sleep 0.1
                    done
                    """
                ),
                encoding="utf-8",
            )
            fake_xcrun.chmod(0o755)

            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{root}:{env['PATH']}",
                    "FAKE_FINALIZED_PATH": str(finalized_path),
                    "FAKE_STARTED_PATH": str(started_path),
                    "AI_UI_VIDEO_STOP_TIMEOUT_SECONDS": "5",
                }
            )

            subprocess.run(
                [
                    "bash",
                    str(SCRIPT_PATH),
                    "start",
                    str(pid_path),
                    "test-udid",
                    str(video_path),
                ],
                cwd=REPO_ROOT,
                env=env,
                check=True,
            )

            deadline = time.monotonic() + 3
            while not started_path.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(started_path.exists())

            started_at = time.monotonic()
            subprocess.run(
                ["bash", str(SCRIPT_PATH), "stop", str(pid_path)],
                cwd=REPO_ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            elapsed = time.monotonic() - started_at

            self.assertTrue(finalized_path.exists())
            self.assertGreaterEqual(elapsed, 0.8)
            self.assertFalse(pid_path.exists())

    def test_start_pid_write_failure_kills_the_entire_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_xcrun = root / "xcrun"
            descendant_marker = root / "descendant-finished"
            pid_path = root / "record-video.pid"
            video_path = root / "video.mp4"
            python_hook_dir = root / "python-hook"
            python_hook_dir.mkdir()

            fake_xcrun.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    trap 'exit 0' TERM
                    (trap '' TERM; sleep 1; touch "$FAKE_DESCENDANT_MARKER") &
                    while true; do
                      sleep 0.1
                    done
                    """
                ),
                encoding="utf-8",
            )
            fake_xcrun.chmod(0o755)

            (python_hook_dir / "sitecustomize.py").write_text(
                """import os
import pathlib

_original_write_text = pathlib.Path.write_text

def _write_text(self, *args, **kwargs):
    if str(self) == os.environ.get("FAIL_PATH_WRITE"):
        raise OSError("injected PID write failure")
    return _original_write_text(self, *args, **kwargs)

pathlib.Path.write_text = _write_text
""",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{root}:{env['PATH']}",
                    "PYTHONPATH": str(python_hook_dir),
                    "FAIL_PATH_WRITE": str(pid_path),
                    "FAKE_DESCENDANT_MARKER": str(descendant_marker),
                    "AI_UI_VIDEO_START_CLEANUP_TIMEOUT_SECONDS": "0.1",
                }
            )

            completed = subprocess.run(
                [
                    "bash",
                    str(SCRIPT_PATH),
                    "start",
                    str(pid_path),
                    "test-udid",
                    str(video_path),
                ],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
            time.sleep(1.1)

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("injected PID write failure", completed.stderr)
            self.assertFalse(descendant_marker.exists())
            self.assertFalse(pid_path.exists())


if __name__ == "__main__":
    unittest.main()
