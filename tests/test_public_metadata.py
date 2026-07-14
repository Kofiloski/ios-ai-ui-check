from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class PublicMetadataTests(unittest.TestCase):
    def test_documented_release_is_consistent_across_public_entry_points(self) -> None:
        citation = (REPO_ROOT / "CITATION.cff").read_text(encoding="utf-8")
        version_match = re.search(r"^version:\s*['\"]?([^'\"\s]+)", citation, re.MULTILINE)
        self.assertIsNotNone(version_match)
        assert version_match is not None
        release_tag = f"v{version_match.group(1)}"

        for relative_path in (
            "README.md",
            "llms.txt",
            "examples/README.md",
            "examples/deterministic-pr-check.yml",
        ):
            with self.subTest(path=relative_path):
                content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
                self.assertIn(release_tag, content)
                self.assertNotIn("OWNER_OR_ORG", content)

    def test_readme_relative_links_resolve(self) -> None:
        for relative_path in ("README.md", "examples/README.md"):
            document_path = REPO_ROOT / relative_path
            content = document_path.read_text(encoding="utf-8")
            targets = re.findall(r"\[[^\]]+\]\(([^)]+)\)", content)

            for target in targets:
                if "://" in target or target.startswith("#"):
                    continue
                local_target = target.split("#", maxsplit=1)[0]
                with self.subTest(document=relative_path, target=target):
                    self.assertTrue((document_path.parent / local_target).exists())

    def test_action_marketplace_description_and_branding_are_present(self) -> None:
        action = (REPO_ROOT / "action.yml").read_text(encoding="utf-8")
        description_match = re.search(r"^description:\s*(.+)$", action, re.MULTILINE)

        self.assertIsNotNone(description_match)
        assert description_match is not None
        self.assertLessEqual(len(description_match.group(1)), 125)
        self.assertIn("author: Kristijan Kofiloski", action)
        self.assertIn("branding:\n  icon: check-circle\n  color: blue", action)


if __name__ == "__main__":
    unittest.main()
