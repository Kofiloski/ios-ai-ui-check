from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "boot-simulator.sh"


class BootSimulatorScriptTests(unittest.TestCase):
    def test_fast_path_writes_shell_safe_environment_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_xcrun = root / "xcrun"
            output_path = root / "nested" / "simulator.env"
            fake_xcrun.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            fake_xcrun.chmod(0o755)

            expected = {
                "AI_UI_SIMULATOR_UDID": "UDID-'quoted'",
                "AI_UI_SIMULATOR_DEVICE_NAME": "iPhone Developer's Edition",
                "AI_UI_SIMULATOR_RUNTIME_ID": "runtime with spaces",
                "AI_UI_SIMULATOR_RUNTIME_NAME": "iOS 26.2\nPreview",
            }
            env = os.environ.copy()
            env.update(expected)
            env.update(
                {
                    "PATH": f"{root}:{env['PATH']}",
                    "SIMULATOR_NAME": "unused-fast-path-name",
                }
            )

            subprocess.run(
                ["bash", str(SCRIPT_PATH), str(output_path)],
                cwd=REPO_ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            probe = textwrap.dedent(
                """\
                source "$1"
                python3 - <<'PY'
                import json
                import os
                keys = (
                    "AI_UI_SIMULATOR_UDID",
                    "AI_UI_SIMULATOR_DEVICE_NAME",
                    "AI_UI_SIMULATOR_RUNTIME_ID",
                    "AI_UI_SIMULATOR_RUNTIME_NAME",
                )
                print(json.dumps({key: os.environ[key] for key in keys}))
                PY
                """
            )
            result = subprocess.run(
                ["bash", "-c", probe, "bash", str(output_path)],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertEqual(json.loads(result.stdout), expected)


if __name__ == "__main__":
    unittest.main()
