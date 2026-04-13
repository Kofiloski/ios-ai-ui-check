#!/usr/bin/env python3
"""Shared scenario contract and repo discovery helpers for ios-ai-ui-check."""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


SUPPORTED_ACTIONS = (
    "launch",
    "tap",
    "type",
    "wait",
    "assertVisible",
    "assertText",
    "screenshot",
)

SOURCE_SUFFIXES = {".swift", ".m", ".mm", ".h"}
EXCLUDED_PATH_PARTS = {
    ".build",
    ".derivedData",
    ".git",
    ".swiftpm",
    "Build",
    "Carthage",
    "DerivedData",
    "Pods",
    "SourcePackages",
    "build",
    "node_modules",
    "vendor",
    "xcuserdata",
}

ACCESSIBILITY_IDENTIFIER_PATTERNS = (
    re.compile(r"\.accessibilityIdentifier\(\s*\"([^\"]+)\"\s*\)"),
    re.compile(r"\baccessibilityIdentifier\s*=\s*@?\"([^\"]+)\""),
)
ACCESSIBILITY_LABEL_PATTERNS = (
    re.compile(r"\.accessibilityLabel\(\s*\"([^\"]+)\"\s*\)"),
    re.compile(r"\baccessibilityLabel\s*=\s*@?\"([^\"]+)\""),
)
ENV_KEY_PATTERN = re.compile(r'"([A-Z][A-Z0-9_]{3,})"')
LAUNCH_ARGUMENT_PATTERN = re.compile(r'"(-{1,2}[A-Za-z][A-Za-z0-9_-]*)"')
UI_TREE_IDENTIFIER_PATTERN = re.compile(r"identifier:\s*'([^']+)'")

SCENARIO_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://example.com/ios-ai-ui-check/scenario.schema.json",
    "title": "iOS AI UI Check Scenario",
    "type": "object",
    "additionalProperties": False,
    "required": ["steps"],
    "properties": {
        "name": {"type": "string"},
        "description": {"type": ["string", "null"]},
        "steps": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["action"],
                "properties": {
                    "action": {"type": "string", "enum": list(SUPPORTED_ACTIONS)},
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "text": {"type": "string"},
                    "output": {"type": "string"},
                    "seconds": {"type": "number"},
                    "wait_seconds": {"type": "number"},
                    "timeout": {"type": "number"},
                    "arguments": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "environment": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                    },
                },
            },
        },
    },
}


class ScenarioContractError(ValueError):
    """Scenario payload or planner output violated the contract."""


def read_text(path: Path, fallback: str = "") -> str:
    if not path.exists() or path.is_dir():
        return fallback
    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or path.is_dir():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_schema_json(path: Path) -> None:
    write_json(path, SCENARIO_SCHEMA)


def iter_source_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix in SOURCE_SUFFIXES else []

    files: list[Path] = []
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in EXCLUDED_PATH_PARTS]
        base_path = Path(current_root)
        for filename in filenames:
            path = base_path / filename
            if path.suffix in SOURCE_SUFFIXES:
                files.append(path)
    return sorted(files)


def collect_accessibility_ids(repo_root: Path) -> set[str]:
    identifiers: set[str] = set()

    for path in iter_source_files(repo_root):
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="utf-8", errors="ignore")

        for pattern in ACCESSIBILITY_IDENTIFIER_PATTERNS:
            for identifier in pattern.findall(content):
                if r"\(" in identifier:
                    continue
                identifiers.add(identifier)

    return identifiers


def collect_accessibility_strings(repo_root: Path) -> tuple[list[str], list[str]]:
    identifiers: set[str] = set()
    labels: set[str] = set()

    for path in iter_source_files(repo_root):
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="utf-8", errors="ignore")

        for pattern in ACCESSIBILITY_IDENTIFIER_PATTERNS:
            for identifier in pattern.findall(content):
                if r"\(" in identifier:
                    continue
                identifiers.add(identifier)

        for pattern in ACCESSIBILITY_LABEL_PATTERNS:
            labels.update(pattern.findall(content))

    return sorted(identifiers), sorted(labels)


def collect_launch_hints(repo_root: Path) -> tuple[list[str], list[str]]:
    environment_keys: set[str] = set()
    launch_arguments: set[str] = set()

    for path in iter_source_files(repo_root):
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="utf-8", errors="ignore")

        environment_keys.update(
            key
            for key in ENV_KEY_PATTERN.findall(content)
            if "AUTOMATION" in key
            or "UITEST" in key
            or "UI_TEST" in key
            or key.endswith("_TESTING")
        )
        launch_arguments.update(LAUNCH_ARGUMENT_PATTERN.findall(content))

    return sorted(environment_keys), sorted(launch_arguments)


def collect_ui_tree_identifiers(path: Path) -> set[str]:
    payload = read_json(path)
    if not payload:
        return set()

    hierarchy_description = payload.get("hierarchyDescription") or ""
    return set(UI_TREE_IDENTIFIER_PATTERN.findall(hierarchy_description))


def summarize_ui_tree(path: Path) -> str:
    payload = read_json(path)
    if not payload:
        return "(unavailable)"

    hierarchy_description = (payload.get("hierarchyDescription") or "").strip()
    if not hierarchy_description:
        return f"- app state: {payload.get('appState', 'unknown')}\n- hierarchy snapshot unavailable"

    lines = [line.strip() for line in hierarchy_description.splitlines() if line.strip()]
    selected: list[str] = []
    for line in lines:
        if len(selected) >= 120:
            break
        normalized = re.sub(r"\s+", " ", line)
        if (
            "identifier:" in normalized
            or "label:" in normalized
            or "value:" in normalized
            or "Button" in normalized
            or "TextField" in normalized
            or "StaticText" in normalized
            or "NavigationBar" in normalized
            or "TabBar" in normalized
            or "CollectionView" in normalized
        ):
            selected.append(f"- {normalized[:240]}")

    if not selected:
        selected = [f"- {re.sub(r'\\s+', ' ', line)[:240]}" for line in lines[:80]]

    return "\n".join(
        [
            f"- app state: {payload.get('appState', 'unknown')}",
            "- current hierarchy excerpt:",
            *selected,
        ]
    )


def render_markdown_list(items: list[str], *, limit: int = 120) -> str:
    if not items:
        return "- none"
    return "\n".join(f"- {item}" for item in items[:limit])


def collect_documented_text(config_dir: Path, planner_context_path: Path) -> str:
    parts: list[str] = []

    planner_context = read_text(planner_context_path)
    if planner_context:
        parts.append(planner_context)

    if config_dir.exists():
        for path in sorted(config_dir.glob("*.json")):
            parts.append(read_text(path))

    return "\n".join(parts)


def is_state_dependent(identifier: str) -> bool:
    lowered = identifier.lower()
    return any(
        token in lowered
        for token in (
            "empty",
            "placeholder",
            "sheet",
            "modal",
            "draft",
            "processing",
            "paywall",
        )
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_scenario_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ScenarioContractError("Scenario payload must be a JSON object")

    allowed_root_fields = {"name", "description", "steps"}
    extra_root_fields = sorted(set(payload.keys()) - allowed_root_fields)
    if extra_root_fields:
        raise ScenarioContractError(
            f"Scenario payload contains unsupported top-level fields: {', '.join(extra_root_fields)}"
        )

    name = payload.get("name")
    if name is not None and not isinstance(name, str):
        raise ScenarioContractError("Scenario payload 'name' must be a string when provided")

    description = payload.get("description")
    if description is not None and not isinstance(description, str):
        raise ScenarioContractError("Scenario payload 'description' must be a string when provided")

    steps = payload.get("steps")
    if not isinstance(steps, list):
        raise ScenarioContractError("Scenario payload must contain a 'steps' array")
    if not steps:
        raise ScenarioContractError("Scenario payload 'steps' array cannot be empty")

    allowed_step_fields = {
        "action",
        "id",
        "label",
        "text",
        "output",
        "seconds",
        "wait_seconds",
        "timeout",
        "arguments",
        "environment",
    }

    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ScenarioContractError(f"Scenario step {index} must be an object")

        extra_step_fields = sorted(set(step.keys()) - allowed_step_fields)
        if extra_step_fields:
            raise ScenarioContractError(
                f"Scenario step {index} contains unsupported fields: {', '.join(extra_step_fields)}"
            )

        action = step.get("action")
        if not isinstance(action, str) or not action.strip():
            raise ScenarioContractError(
                f"Scenario step {index} must contain a non-empty string 'action'"
            )
        if action not in SUPPORTED_ACTIONS:
            raise ScenarioContractError(
                f"Scenario step {index} action '{action}' is unsupported. "
                f"Allowed actions: {', '.join(SUPPORTED_ACTIONS)}"
            )

        for key in ("id", "label", "text", "output"):
            value = step.get(key)
            if value is not None and not isinstance(value, str):
                raise ScenarioContractError(
                    f"Scenario step {index} field '{key}' must be a string when provided"
                )

        for key in ("seconds", "wait_seconds", "timeout"):
            value = step.get(key)
            if value is not None and not _is_number(value):
                raise ScenarioContractError(
                    f"Scenario step {index} field '{key}' must be numeric when provided"
                )

        arguments = step.get("arguments")
        if arguments is not None:
            if not isinstance(arguments, list) or not all(isinstance(item, str) for item in arguments):
                raise ScenarioContractError(
                    f"Scenario step {index} field 'arguments' must be an array of strings when provided"
                )

        environment = step.get("environment")
        if environment is not None:
            if not isinstance(environment, dict):
                raise ScenarioContractError(
                    f"Scenario step {index} field 'environment' must be an object when provided"
                )
            for env_key, env_value in environment.items():
                if not isinstance(env_key, str) or not isinstance(env_value, str):
                    raise ScenarioContractError(
                        f"Scenario step {index} field 'environment' must contain only string keys and values"
                    )


def load_and_validate_scenario(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScenarioContractError(f"Scenario payload is not valid JSON: {exc}") from exc

    validate_scenario_payload(payload)
    return payload


def validate_generated_scenario(
    scenario: dict[str, Any],
    *,
    known_identifiers: list[str],
    before_planning_ui_tree_identifiers: set[str],
    documented_text: str,
) -> None:
    known_identifier_set = set(known_identifiers)
    if not known_identifier_set:
        return

    unknown_ids: list[tuple[int, str, list[str]]] = []
    risky_ids: list[tuple[int, str]] = []

    for index, step in enumerate(scenario.get("steps", [])):
        step_id = step.get("id")
        if not isinstance(step_id, str) or not step_id:
            continue

        if step_id not in known_identifier_set:
            suggestions = difflib.get_close_matches(
                step_id,
                sorted(known_identifier_set),
                n=3,
                cutoff=0.45,
            )
            unknown_ids.append((index, step_id, suggestions))
            continue

        if is_state_dependent(step_id):
            if step_id in before_planning_ui_tree_identifiers:
                continue
            if step_id in documented_text:
                continue
            risky_ids.append((index, step_id))

    if not unknown_ids and not risky_ids:
        return

    messages: list[str] = []
    if unknown_ids:
        messages.append(
            "Planner output referenced accessibility identifiers that were not found in source-discovered accessibilityIdentifier literals:"
        )
        for index, step_id, suggestions in unknown_ids:
            if suggestions:
                messages.append(
                    f"- step {index} id '{step_id}' is unknown. Closest known ids: {', '.join(suggestions)}"
                )
            else:
                messages.append(f"- step {index} id '{step_id}' is unknown.")

    if risky_ids:
        messages.append(
            "Planner output referenced state-dependent identifiers that were not visible in the inspected UI and were not documented in planner guidance or the checked-in scenario example:"
        )
        for index, step_id in risky_ids:
            messages.append(
                f"- step {index} id '{step_id}' looks conditional. Document it explicitly or use a more stable entry point."
            )

    raise ScenarioContractError("\n".join(messages))


def build_repo_scan_payload(repo_root: Path) -> dict[str, Any]:
    identifiers, labels = collect_accessibility_strings(repo_root)
    environment_keys, launch_arguments = collect_launch_hints(repo_root)
    return {
        "repo_root": str(repo_root),
        "identifiers": identifiers,
        "labels": labels,
        "launch_environment_keys": environment_keys,
        "launch_arguments": launch_arguments,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Shared scenario contract and repo discovery helpers for ios-ai-ui-check."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    write_schema_parser = subparsers.add_parser(
        "write-schema",
        help="Write the canonical scenario schema JSON to a file.",
    )
    write_schema_parser.add_argument("--output", type=Path, required=True)

    validate_parser = subparsers.add_parser(
        "validate-scenario",
        help="Validate a scenario JSON file against the canonical contract.",
    )
    validate_parser.add_argument("scenario_path", type=Path)

    planner_validate_parser = subparsers.add_parser(
        "validate-generated-scenario",
        help="Validate planner output against known source identifiers and documented state guidance.",
    )
    planner_validate_parser.add_argument("scenario_path", type=Path)
    planner_validate_parser.add_argument("--repo-root", type=Path, required=True)
    planner_validate_parser.add_argument("--planner-context", type=Path, required=True)
    planner_validate_parser.add_argument("--config-dir", type=Path, required=True)
    planner_validate_parser.add_argument("--before-planning-ui-tree", type=Path)

    scan_parser = subparsers.add_parser(
        "scan-repo",
        help="Emit discovered accessibility and launch hints for a repo.",
    )
    scan_parser.add_argument("repo_root", type=Path)

    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    try:
        if args.command == "write-schema":
            write_schema_json(args.output.resolve())
            return 0

        if args.command == "validate-scenario":
            load_and_validate_scenario(args.scenario_path.resolve())
            return 0

        if args.command == "validate-generated-scenario":
            scenario = load_and_validate_scenario(args.scenario_path.resolve())
            repo_root = args.repo_root.resolve()
            planner_context_path = args.planner_context.resolve()
            config_dir = args.config_dir.resolve()
            before_planning_ui_tree_path = (
                args.before_planning_ui_tree.resolve()
                if args.before_planning_ui_tree is not None
                else Path("")
            )

            validate_generated_scenario(
                scenario,
                known_identifiers=sorted(collect_accessibility_ids(repo_root)),
                before_planning_ui_tree_identifiers=collect_ui_tree_identifiers(
                    before_planning_ui_tree_path
                ),
                documented_text=collect_documented_text(config_dir, planner_context_path),
            )
            return 0

        if args.command == "scan-repo":
            print(json.dumps(build_repo_scan_payload(args.repo_root.resolve()), indent=2))
            return 0

        raise ScenarioContractError(f"Unsupported command: {args.command}")
    except ScenarioContractError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
