from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest import mock
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
            "name": "Launch app",
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

    def test_validate_scenario_payload_accepts_each_supported_action_shape(self) -> None:
        payload = {
            "name": "Exercise the runtime contract",
            "steps": [
                {
                    "action": "launch",
                    "arguments": ["-automation"],
                    "environment": {"AUTOMATION_ROUTE": "home"},
                    "wait_seconds": 0,
                },
                {"action": "tap", "id": "home.primary", "timeout": 1},
                {"action": "type", "text": "hello"},
                {"action": "wait", "seconds": 0},
                {"action": "assertVisible", "label": "Home"},
                {"action": "assertText", "text": "Welcome"},
                {"action": "screenshot", "output": "screens/home.png"},
            ],
        }

        ai_ui_contract.validate_scenario_payload(payload)

    def test_validate_scenario_payload_rejects_missing_or_blank_name(self) -> None:
        for name in (None, "", "   "):
            with self.subTest(name=name):
                payload = {"steps": [{"action": "screenshot"}]}
                if name is not None:
                    payload["name"] = name

                with self.assertRaises(ai_ui_contract.ScenarioContractError) as context:
                    ai_ui_contract.validate_scenario_payload(payload)

                self.assertIn("non-empty string 'name'", str(context.exception))

    def test_validate_scenario_payload_rejects_unknown_step_field(self) -> None:
        payload = {
            "name": "Invalid tap",
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

    def test_validate_scenario_payload_rejects_action_specific_contract_violations(self) -> None:
        invalid_steps = [
            ({"action": "launch", "timeout": 1}, "unsupported fields"),
            ({"action": "tap"}, "requires a non-empty 'id' or 'label'"),
            ({"action": "assertVisible", "id": ""}, "must be non-empty"),
            ({"action": "type", "text": ""}, "must be non-empty"),
            ({"action": "assertText"}, "requires non-empty 'text'"),
            ({"action": "wait"}, "requires nonnegative 'seconds'"),
        ]

        for step, expected_message in invalid_steps:
            with self.subTest(step=step):
                with self.assertRaises(ai_ui_contract.ScenarioContractError) as context:
                    ai_ui_contract.validate_scenario_payload(
                        {"name": "Invalid scenario", "steps": [step]}
                    )

                self.assertIn(expected_message, str(context.exception))

    def test_validate_scenario_payload_rejects_explicit_null_step_fields(self) -> None:
        invalid_steps = [
            ({"action": "launch", "arguments": None}, "array of strings"),
            ({"action": "launch", "environment": None}, "must be an object"),
            ({"action": "launch", "wait_seconds": None}, "finite number"),
            ({"action": "tap", "id": "home.primary", "timeout": None}, "finite number"),
            ({"action": "type", "text": "hello", "id": None}, "must be a string"),
            ({"action": "wait", "seconds": None}, "finite number"),
            ({"action": "screenshot", "output": None}, "must be a string"),
        ]

        for step, expected_message in invalid_steps:
            with self.subTest(step=step):
                with self.assertRaises(ai_ui_contract.ScenarioContractError) as context:
                    ai_ui_contract.validate_scenario_payload(
                        {"name": "Invalid null field", "steps": [step]}
                    )

                self.assertIn(expected_message, str(context.exception))

    def test_validate_scenario_payload_rejects_unsafe_screenshot_outputs(self) -> None:
        for output in (
            "/tmp/escaped.png",
            "../escaped.png",
            "nested/../../escaped.png",
            r"C:\escaped.png",
            r"nested\..\escaped.png",
            ".",
            "./",
            ".\\",
            "././",
        ):
            with self.subTest(output=output):
                with self.assertRaises(ai_ui_contract.ScenarioContractError) as context:
                    ai_ui_contract.validate_scenario_payload(
                        {
                            "name": "Unsafe screenshot",
                            "steps": [{"action": "screenshot", "output": output}],
                        }
                    )

                self.assertIn("screenshot output", str(context.exception))

    def test_validate_scenario_payload_rejects_nonfinite_or_out_of_range_durations(self) -> None:
        invalid_steps = [
            {"action": "wait", "seconds": -1},
            {"action": "wait", "seconds": float("nan")},
            {"action": "launch", "wait_seconds": float("inf")},
            {"action": "tap", "id": "home.primary", "timeout": 0},
            {"action": "tap", "id": "home.primary", "timeout": float("inf")},
        ]

        for step in invalid_steps:
            with self.subTest(step=step):
                with self.assertRaises(ai_ui_contract.ScenarioContractError):
                    ai_ui_contract.validate_scenario_payload(
                        {"name": "Invalid duration", "steps": [step]}
                    )

    def test_openai_planner_schema_is_strict_and_uses_environment_pairs(self) -> None:
        unsupported_keywords = {"not", "anyOf", "oneOf", "allOf", "if", "then", "else"}

        def assert_strict_objects(schema: object) -> None:
            if isinstance(schema, list):
                for value in schema:
                    assert_strict_objects(value)
                return
            if not isinstance(schema, dict):
                return

            self.assertFalse(
                unsupported_keywords.intersection(schema),
                f"strict planner schema uses an unsupported keyword: {schema}",
            )
            if schema.get("type") == "object":
                self.assertIs(schema.get("additionalProperties"), False)
                self.assertEqual(
                    set(schema.get("required", [])),
                    set(schema.get("properties", {})),
                )
            for value in schema.values():
                assert_strict_objects(value)

        assert_strict_objects(ai_ui_contract.OPENAI_PLANNER_SCHEMA)

        step_schema = ai_ui_contract.OPENAI_PLANNER_SCHEMA["properties"]["steps"]["items"]
        environment_schema = step_schema["properties"]["environment"]
        self.assertEqual(environment_schema["type"], ["array", "null"])
        self.assertEqual(
            set(environment_schema["items"]["properties"]),
            {"key", "value"},
        )

    def test_normalize_openai_planner_scenario_converts_environment_and_drops_nulls(self) -> None:
        def planner_step(action: str, **overrides: object) -> dict[str, object]:
            step: dict[str, object] = {
                "action": action,
                "id": None,
                "label": None,
                "text": None,
                "output": None,
                "seconds": None,
                "wait_seconds": None,
                "timeout": None,
                "arguments": None,
                "environment": None,
            }
            step.update(overrides)
            return step

        planner_payload = {
            "name": "Strict planner scenario",
            "description": None,
            "steps": [
                planner_step(
                    "launch",
                    arguments=[],
                    environment=[
                        {"key": "AUTOMATION_ROUTE", "value": "home"},
                        {"key": "UITESTING", "value": "1"},
                    ],
                    wait_seconds=2,
                ),
                planner_step("screenshot", output="screens/home.png"),
            ],
        }

        normalized = ai_ui_contract.normalize_openai_planner_scenario(planner_payload)

        self.assertEqual(
            normalized,
            {
                "name": "Strict planner scenario",
                "steps": [
                    {
                        "action": "launch",
                        "arguments": [],
                        "wait_seconds": 2,
                        "environment": {
                            "AUTOMATION_ROUTE": "home",
                            "UITESTING": "1",
                        },
                    },
                    {"action": "screenshot", "output": "screens/home.png"},
                ],
            },
        )

    def test_normalize_openai_planner_scenario_rejects_duplicate_environment_keys(self) -> None:
        step = {
            "action": "launch",
            "id": None,
            "label": None,
            "text": None,
            "output": None,
            "seconds": None,
            "wait_seconds": None,
            "timeout": None,
            "arguments": [],
            "environment": [
                {"key": "UITESTING", "value": "1"},
                {"key": "UITESTING", "value": "0"},
            ],
        }

        with self.assertRaises(ai_ui_contract.ScenarioContractError) as context:
            ai_ui_contract.normalize_openai_planner_scenario(
                {"name": "Duplicate environment", "description": None, "steps": [step]}
            )

        self.assertIn("duplicate key", str(context.exception))

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

    def test_source_discovery_ignores_comments_and_examples_and_supports_common_literal_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            swift_path = repo_root / "Sources" / "Example.swift"
            swift_path.parent.mkdir(parents=True)
            swift_path.write_text(
                '''
                // .accessibilityIdentifier("fake.comment")
                /*
                 .accessibilityLabel("Fake Block Label")
                 let flag = "FAKE_AUTOMATION_ROUTE"
                 let argument = "-fake-argument"
                */
                let documentation = """
                .accessibilityIdentifier("fake.example")
                .accessibilityLabel("Fake Example Label")
                """
                let pattern = #/ .accessibilityIdentifier("fake.regex") /#
                let standardPattern = /.accessibilityIdentifier("fake.standard.regex")/
                let quotient = total / count
                guard /.accessibilityIdentifier("fake.guard.regex")/.wholeMatch(in: input) != nil else { return }

                Text("Save")
                    .accessibilityIdentifier(
                        #"sample.save"#
                    )
                    .accessibilityLabel("Save Recipe")
                Text("Dynamic")
                    .accessibilityIdentifier("sample.row.\\(item.id)")

                let environmentKey = #"SAMPLE_AUTOMATION_ROUTE"#
                let launchArgument = "-automation-home"
                ''',
                encoding="utf-8",
            )

            objc_path = repo_root / "Sources" / "Legacy.m"
            objc_path.write_text(
                '''
                [button setAccessibilityIdentifier:@"sample.legacy.save"];
                [button setAccessibilityLabel:@"Legacy Save"];
                ''',
                encoding="utf-8",
            )

            identifiers, labels = ai_ui_contract.collect_accessibility_strings(repo_root)
            env_keys, launch_arguments = ai_ui_contract.collect_launch_hints(repo_root)

            self.assertEqual(
                identifiers,
                ["sample.legacy.save", "sample.save"],
            )
            self.assertEqual(labels, ["Legacy Save", "Save Recipe"])
            self.assertEqual(env_keys, ["SAMPLE_AUTOMATION_ROUTE"])
            self.assertEqual(launch_arguments, ["-automation-home"])

    def test_source_lexer_distinguishes_standard_regex_literals_from_division(self) -> None:
        source = '''
        let quotient = total / count
        let regex = /.accessibilityIdentifier("fake.regex")/
        '''

        code_mask, _ = ai_ui_contract._lex_source(source)

        self.assertIn("total / count", code_mask)
        self.assertNotIn("fake.regex", code_mask)

    def test_accessibility_discovery_lexes_each_source_once_for_ids_and_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            source_path = repo_root / "Sources" / "LiteralHeavy.swift"
            source_path.parent.mkdir(parents=True)
            unrelated_literals = "\n".join(
                f'let value{index} = "literal-{index}"' for index in range(2000)
            )
            source_path.write_text(
                unrelated_literals
                + '''
                Text("Save")
                    .accessibilityIdentifier("sample.save")
                    .accessibilityLabel("Save")
                ''',
                encoding="utf-8",
            )

            with mock.patch.object(
                ai_ui_contract,
                "_lex_source",
                wraps=ai_ui_contract._lex_source,
            ) as lex_source:
                identifiers, labels = ai_ui_contract.collect_accessibility_strings(repo_root)

            self.assertEqual(identifiers, ["sample.save"])
            self.assertEqual(labels, ["Save"])
            self.assertEqual(lex_source.call_count, 1)

    def test_validate_generated_scenario_reports_unknown_and_risky_ids(self) -> None:
        scenario = {
            "name": "Invalid identifiers",
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
