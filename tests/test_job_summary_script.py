from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "write-job-summary.py"


class JobSummaryScriptTests(unittest.TestCase):
    def run_writer(self, summary: str, *, status: str = "passed") -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "summary.md"
            output = root / "github-summary.md"
            source.write_text(summary, encoding="utf-8")
            env = os.environ.copy()
            env["GITHUB_STEP_SUMMARY"] = str(output)

            subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--status",
                    status,
                    "--summary-path",
                    str(source),
                    "--artifact-url",
                    "https://example.com/artifact",
                ],
                cwd=REPO_ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            return output.read_bytes()

    def test_writes_status_artifact_and_summary(self) -> None:
        output = self.run_writer("## Result\n\n- Scenario passed ✅\n")
        text = output.decode("utf-8")

        self.assertIn("Status: `passed`", text)
        self.assertIn("[ios-ai-ui-check](https://example.com/artifact)", text)
        self.assertIn("Scenario passed ✅", text)

    def test_truncates_oversized_summary_on_utf8_boundary(self) -> None:
        output = self.run_writer("✅" * 400_000)

        self.assertLessEqual(len(output), 900_000)
        self.assertIn("Full summary truncated", output.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
