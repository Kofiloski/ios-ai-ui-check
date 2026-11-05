from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ai_ui_contract as contract


class ChangeContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Fixture")
        self.commit("one")
        self.git("tag", "base")
        self.commit("two")
        self.commit("three")
        self.git("tag", "head")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True, stderr=subprocess.PIPE).strip()

    def commit(self, text):
        (self.repo / f"{text}.txt").write_text(text)
        self.git("add", ".")
        self.git("commit", "-qm", text)

    def test_explicit_release_covers_all_commits_and_notes(self):
        notes = self.repo / "notes.md"
        notes.write_text("Two release changes.")
        context = contract.collect_change_context(self.repo, base_ref="base", head_ref="head", release_notes_path=notes)
        self.assertEqual(context["changed_files"], ["three.txt", "two.txt"])
        self.assertEqual(context["release_notes"], notes.read_text())
        self.assertEqual(context["head_sha"], self.git("rev-parse", "HEAD"))
        self.assertFalse(context["diff_truncated"])

    def test_missing_explicit_ref_does_not_fall_back(self):
        with self.assertRaisesRegex(contract.ScenarioContractError, "unavailable"):
            contract.collect_change_context(self.repo, base_ref="absent", head_ref="head")

    def test_requires_both_refs_and_matching_checkout(self):
        with self.assertRaisesRegex(contract.ScenarioContractError, "together"):
            contract.collect_change_context(self.repo, base_ref="base")
        with self.assertRaisesRegex(contract.ScenarioContractError, "match"):
            contract.collect_change_context(self.repo, base_ref="head", head_ref="base")

    def test_pr_missing_history_is_an_error_without_parent_fallback(self):
        with self.assertRaisesRegex(contract.ScenarioContractError, "unavailable"):
            contract.collect_change_context(self.repo, event={"pull_request": {"base": {"sha": "absent"}, "head": {"sha": "head"}}})

    def test_empty_explicit_diff_and_notes_fail(self):
        with self.assertRaisesRegex(contract.ScenarioContractError, "no source changes"):
            contract.collect_change_context(self.repo, base_ref="head", head_ref="head")
        notes = self.repo / "empty.md"
        notes.write_text("")
        with self.assertRaisesRegex(contract.ScenarioContractError, "empty"):
            contract.collect_change_context(self.repo, base_ref="base", head_ref="head", release_notes_path=notes)

    def test_truncation_is_visible_and_full_diff_preserved(self):
        context = contract.collect_change_context(self.repo, base_ref="base", head_ref="head", diff_limit=10)
        self.assertTrue(context["diff_truncated"])
        self.assertEqual(len(context["diff"]), 10)
        self.assertIn("two.txt", context["_full_diff"])
        self.assertIn("truncated: true", contract.change_context_summary(context))
        self.assertIn("Other release changes remain unverified", contract.change_context_summary(context))

    def test_shallow_manual_run_discloses_missing_context(self):
        shallow = self.repo / "shallow"
        subprocess.run(["git", "clone", "-q", "--depth", "1", self.repo.as_uri(), str(shallow)], check=True)
        context = contract.collect_change_context(shallow)
        self.assertFalse(context["available"])
        self.assertIn("unavailable", contract.change_context_summary(context))

    def test_release_smoke_only_is_rejected_but_assertion_is_accepted(self):
        scenario = {"name": "Smoke", "steps": [{"action": "launch"}, {"action": "screenshot"}]}
        with self.assertRaisesRegex(contract.ScenarioContractError, "insufficient"):
            contract.require_release_assertions(scenario, {"source": "explicit"})
        scenario["steps"].append({"action": "assertText", "text": "Second page"})
        contract.require_release_assertions(scenario, {"source": "explicit"})


if __name__ == "__main__":
    unittest.main()
