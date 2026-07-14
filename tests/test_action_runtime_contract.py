from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTION_SURFACES = (
    ROOT / "action.yml",
    ROOT / ".github" / "workflows",
    ROOT / "templates",
)
MINIMUM_NODE24_MAJORS = {
    "actions/checkout": 5,
    "actions/setup-python": 6,
    "actions/upload-artifact": 6,
    "actions/download-artifact": 7,
}
ACTION_REFERENCE = re.compile(
    r"^[ \t]*(?:-[ \t]*)?(?:uses|['\"]uses['\"]):[ \t]*['\"]?"
    r"(?P<action>actions/[a-z0-9_-]+)@(?P<ref>[^'\"\s#]+)",
    re.IGNORECASE | re.MULTILINE,
)
ACTION_MAJOR_REF = re.compile(r"v(?P<major>\d+)(?:\.\d+){0,2}\Z", re.IGNORECASE)
BLOCK_SCALAR_START = re.compile(
    r"^[ ]*(?:-[ ]*)?(?:[A-Za-z0-9_-]+|['\"][^'\"]+['\"]):"
    r"[ ]*[|>][0-9+-]*[ ]*(?:#.*)?$"
)


def action_surface_files() -> list[Path]:
    files: list[Path] = []
    for surface in ACTION_SURFACES:
        if surface.is_file():
            files.append(surface)
        elif surface.is_dir():
            files.extend(
                path
                for path in surface.rglob("*")
                if path.is_file() and path.suffix in {".yml", ".yaml", ".tpl"}
            )
    return files


def action_references(text: str):
    block_parent_indent: int | None = None
    for line in text.splitlines():
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))

        if block_parent_indent is not None:
            if not stripped or indent > block_parent_indent:
                continue
            block_parent_indent = None

        if BLOCK_SCALAR_START.match(line):
            block_parent_indent = indent
            continue

        match = ACTION_REFERENCE.match(line)
        if match:
            yield match


def reviewed_node24_major(action: str, ref: str) -> int:
    minimum = MINIMUM_NODE24_MAJORS.get(action)
    if minimum is None:
        raise ValueError(f"{action} has no reviewed Node 24 minimum")
    version = ACTION_MAJOR_REF.fullmatch(ref)
    if version is None:
        raise ValueError(f"{action}@{ref} requires explicit Node 24 review")
    major = int(version.group("major"))
    if major < minimum:
        raise ValueError(
            f"{action}@{ref} requires at least v{minimum} for Node 24"
        )
    return major


class ActionRuntimeContractTests(unittest.TestCase):
    def test_github_actions_use_node24_compatible_majors(self) -> None:
        checked_references = 0

        for path in action_surface_files():
            text = path.read_text(encoding="utf-8")
            for match in action_references(text):
                action = match.group("action").lower()
                checked_references += 1
                reviewed_node24_major(action, match.group("ref"))

        self.assertGreater(checked_references, 0, "no GitHub Action references were checked")
        self.assertIsNone(
            ACTION_REFERENCE.search("# migrated from uses: actions/setup-python@v5")
        )
        self.assertEqual(
            [
                match.group("ref")
                for match in action_references(
                    "run: |\n  uses: actions/setup-python@v5\n"
                    "- uses: actions/setup-python@v6\n"
                )
            ],
            ["v6"],
        )
        self.assertEqual(
            [
                match.group("ref")
                for match in action_references(
                    '- "uses": actions/setup-python@v5\n'
                )
            ],
            ["v5"],
        )
        with self.assertRaisesRegex(ValueError, "requires explicit Node 24 review"):
            reviewed_node24_major("actions/setup-python", "a" * 40)


if __name__ == "__main__":
    unittest.main()
