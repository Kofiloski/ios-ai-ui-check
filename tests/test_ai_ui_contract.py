from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import ai_ui_contract  # noqa: E402


class AIUIContractTests(unittest.TestCase):
    def test_schema_file_matches_canonical_schema(self) -> None:
        schema_path = REPO_ROOT / "schemas" / "scenario.schema.json"
        schema_payload = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema_payload, ai_ui_contract.SCENARIO_SCHEMA)

    def test_validate_scenario_payload_accepts_minimal_payload(self) -> None:
        payload = {
            "steps": [
                {
                    "action": "launch",
                    "arguments": [],
                    "environment": {},
                    "wait_seconds": 2,
                }
            ]
        }

        ai_ui_contract.validate_scenario_payload(payload)

    def test_validate_scenario_payload_rejects_unknown_step_field(self) -> None:
        payload = {
            "steps": [
                {
                    "action": "tap",
                    "value": "unsupported",
                }
            ]
        }

        with self.assertRaises(ai_ui_contract.ScenarioContractError) as context:
            ai_ui_contract.validate_scenario_payload(payload)

        self.assertIn("unsupported fields", str(context.exception))

    def test_collect_accessibility_and_launch_hints_scan_nested_repo_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            source_path = repo_root / "App" / "Features" / "RecipeView.swift"
            source_path.parent.mkdir(parents=True)
            source_path.write_text(
                """
                import SwiftUI

                struct RecipeView: View {
                    var body: some View {
                        VStack {
                            Button("Analyze") {}
                                .accessibilityIdentifier("cookyard.recipeForm.analyzeVideo")
                                .accessibilityLabel("Analyze Video")
                        }
                    }
                }

                let flag = "-automation-add-recipe"
                let env = "COOKYARD_AUTOMATION_ROUTE"
                let dynamic = "cookyard.recipe.row.\\(recipe.id.uuidString)"
                """,
                encoding="utf-8",
            )

            objc_path = repo_root / "Legacy" / "RecipeViewController.m"
            objc_path.parent.mkdir(parents=True)
            objc_path.write_text(
                """
                self.titleField.accessibilityIdentifier = @"cookyard.recipeForm.title";
                """,
                encoding="utf-8",
            )

            ignored_path = repo_root / "Pods" / "Generated.swift"
            ignored_path.parent.mkdir(parents=True)
            ignored_path.write_text(
                """
                Text("Ignore").accessibilityIdentifier("pods.should.not.scan")
                """,
                encoding="utf-8",
            )

            identifiers, labels = ai_ui_contract.collect_accessibility_strings(repo_root)
            env_keys, launch_arguments = ai_ui_contract.collect_launch_hints(repo_root)

            self.assertEqual(
                identifiers,
                [
                    "cookyard.recipeForm.analyzeVideo",
                    "cookyard.recipeForm.title",
                ],
            )
            self.assertEqual(labels, ["Analyze Video"])
            self.assertEqual(env_keys, ["COOKYARD_AUTOMATION_ROUTE"])
            self.assertEqual(launch_arguments, ["-automation-add-recipe"])

    def test_validate_generated_scenario_reports_unknown_and_risky_ids(self) -> None:
        scenario = {
            "steps": [
                {"action": "tap", "id": "cookyard.recipeForm.unknown"},
                {"action": "tap", "id": "cookyard.paywall.cta"},
            ]
        }

        with self.assertRaises(ai_ui_contract.ScenarioContractError) as context:
            ai_ui_contract.validate_generated_scenario(
                scenario,
                known_identifiers=[
                    "cookyard.recipeForm.analyzeVideo",
                    "cookyard.paywall.cta",
                ],
                before_planning_ui_tree_identifiers=set(),
                documented_text="",
            )

        message = str(context.exception)
        self.assertIn("unknown", message)
        self.assertIn("looks conditional", message)


if __name__ == "__main__":
    unittest.main()
