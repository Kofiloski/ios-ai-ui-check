from __future__ import annotations

from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == "darwin" and shutil.which("xcrun"), "Requires Xcode on macOS")
class SwiftRunnerCompileTests(unittest.TestCase):
    def test_runner_typechecks_in_swift_6_with_simulator_sdk(self) -> None:
        sdk = subprocess.run(
            ["xcrun", "--sdk", "iphonesimulator", "--show-sdk-path"],
            capture_output=True, text=True, check=False,
        )
        if sdk.returncode:
            self.skipTest("Selected developer directory has no iOS Simulator SDK")
        sdk_path = Path(sdk.stdout.strip())
        platform_path = sdk_path.parents[1]
        source = (ROOT / "templates/ScenarioRunnerUITests.swift.tpl").read_text()
        source = source.replace("__SCAFFOLD_HEADER_SWIFT__", "// Runner compile regression check")
        with tempfile.TemporaryDirectory(prefix="ui-runner-compile-") as directory:
            swift_file = Path(directory) / "ScenarioRunnerUITests.swift"
            swift_file.write_text(source)
            result = subprocess.run(
                [
                    "xcrun", "--sdk", "iphonesimulator", "swiftc",
                    "-typecheck", "-swift-version", "6", "-warnings-as-errors",
                    "-sdk", str(sdk_path),
                    "-target", f"{platform.machine()}-apple-ios18.0-simulator",
                    "-F", str(platform_path / "Library/Frameworks"),
                    "-F", str(sdk_path / "Developer/Library/Frameworks"),
                    "-I", str(platform_path / "usr/lib"),
                    str(swift_file),
                ],
                capture_output=True, text=True, check=False,
                timeout=60,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
