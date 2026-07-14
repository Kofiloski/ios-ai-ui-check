#!/usr/bin/env python3
"""Shared scenario contract and repo discovery helpers for ios-ai-ui-check."""

from __future__ import annotations

import argparse
import difflib
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
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

ENV_KEY_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{3,}")
LAUNCH_ARGUMENT_PATTERN = re.compile(r"-{1,2}[A-Za-z][A-Za-z0-9_-]*")
UI_TREE_IDENTIFIER_PATTERN = re.compile(r"identifier:\s*'([^']+)'")

NON_EMPTY_STRING_SCHEMA: dict[str, Any] = {"type": "string", "minLength": 1, "pattern": r"\S"}
TIMEOUT_SCHEMA: dict[str, Any] = {"type": "number", "exclusiveMinimum": 0}
NONNEGATIVE_DURATION_SCHEMA: dict[str, Any] = {"type": "number", "minimum": 0}
SCREENSHOT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "string",
    "minLength": 1,
    "pattern": r"\S",
    "not": {
        "anyOf": [
            {"pattern": r"^(?:/|[A-Za-z]:[\\/]|\\\\)"},
            {"pattern": r"(?:^|[\\/])\.\.(?:[\\/]|$)"},
            {"pattern": r"^\.(?:[\\/]+\.)*[\\/]*$"},
        ]
    },
}


def _runtime_step_schema(
    action: str,
    properties: dict[str, Any],
    *,
    required: tuple[str, ...] = (),
    target_required: bool = False,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["action", *required],
        "properties": {
            "action": {"const": action},
            **properties,
        },
    }
    if target_required:
        schema["anyOf"] = [{"required": ["id"]}, {"required": ["label"]}]
    return schema


TARGET_PROPERTIES: dict[str, Any] = {
    "id": NON_EMPTY_STRING_SCHEMA,
    "label": NON_EMPTY_STRING_SCHEMA,
    "timeout": TIMEOUT_SCHEMA,
}


SCENARIO_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://example.com/ios-ai-ui-check/scenario.schema.json",
    "title": "iOS AI UI Check Scenario",
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "steps"],
    "properties": {
        "name": NON_EMPTY_STRING_SCHEMA,
        "description": {"type": ["string", "null"]},
        "steps": {
            "type": "array",
            "minItems": 1,
            "items": {
                "oneOf": [
                    _runtime_step_schema(
                        "launch",
                        {
                            "arguments": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "environment": {
                                "type": "object",
                                "propertyNames": NON_EMPTY_STRING_SCHEMA,
                                "additionalProperties": {"type": "string"},
                            },
                            "wait_seconds": NONNEGATIVE_DURATION_SCHEMA,
                        },
                    ),
                    _runtime_step_schema(
                        "tap",
                        TARGET_PROPERTIES,
                        target_required=True,
                    ),
                    _runtime_step_schema(
                        "type",
                        {**TARGET_PROPERTIES, "text": NON_EMPTY_STRING_SCHEMA},
                        required=("text",),
                    ),
                    _runtime_step_schema(
                        "wait",
                        {"seconds": NONNEGATIVE_DURATION_SCHEMA},
                        required=("seconds",),
                    ),
                    _runtime_step_schema(
                        "assertVisible",
                        TARGET_PROPERTIES,
                        target_required=True,
                    ),
                    _runtime_step_schema(
                        "assertText",
                        {**TARGET_PROPERTIES, "text": NON_EMPTY_STRING_SCHEMA},
                        required=("text",),
                    ),
                    _runtime_step_schema(
                        "screenshot",
                        {"output": SCREENSHOT_OUTPUT_SCHEMA},
                    ),
                ]
            },
        },
    },
}


_STRICT_OPTIONAL_STRING_SCHEMA: dict[str, Any] = {
    "type": ["string", "null"],
    "minLength": 1,
    "pattern": r"\S",
}
_STRICT_OPTIONAL_SCREENSHOT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": ["string", "null"],
    "minLength": 1,
    "pattern": r"\S",
}
_STRICT_OPTIONAL_DURATION_SCHEMA: dict[str, Any] = {
    "type": ["number", "null"],
    "minimum": 0,
}
_STRICT_OPTIONAL_TIMEOUT_SCHEMA: dict[str, Any] = {
    "type": ["number", "null"],
    "exclusiveMinimum": 0,
}


# OpenAI strict structured outputs require every object property to be required
# and every object to set additionalProperties to false. This wire schema is
# deliberately separate from the provider-neutral runtime scenario schema.
OPENAI_PLANNER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "description", "steps"],
    "properties": {
        "name": NON_EMPTY_STRING_SCHEMA,
        "description": {"type": ["string", "null"]},
        "steps": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
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
                ],
                "properties": {
                    "action": {"type": "string", "enum": list(SUPPORTED_ACTIONS)},
                    "id": _STRICT_OPTIONAL_STRING_SCHEMA,
                    "label": _STRICT_OPTIONAL_STRING_SCHEMA,
                    "text": _STRICT_OPTIONAL_STRING_SCHEMA,
                    "output": _STRICT_OPTIONAL_SCREENSHOT_OUTPUT_SCHEMA,
                    "seconds": _STRICT_OPTIONAL_DURATION_SCHEMA,
                    "wait_seconds": _STRICT_OPTIONAL_DURATION_SCHEMA,
                    "timeout": _STRICT_OPTIONAL_TIMEOUT_SCHEMA,
                    "arguments": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                    },
                    "environment": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["key", "value"],
                            "properties": {
                                "key": NON_EMPTY_STRING_SCHEMA,
                                "value": {"type": "string"},
                            },
                        },
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


@dataclass(frozen=True)
class SourceString:
    start: int
    content_start: int
    content_end: int
    end: int
    interpolation_spans: tuple[tuple[int, int], ...]


def _string_delimiter_at(source: str, index: int) -> tuple[int, int, int] | None:
    cursor = index
    while cursor < len(source) and source[cursor] == "#":
        cursor += 1
    if cursor >= len(source) or source[cursor] != '"':
        return None
    quote_count = 3 if source.startswith('"""', cursor) else 1
    return cursor - index, quote_count, cursor


def _skip_block_comment(source: str, index: int) -> int:
    depth = 1
    cursor = index + 2
    while cursor < len(source) and depth:
        if source.startswith("/*", cursor):
            depth += 1
            cursor += 2
        elif source.startswith("*/", cursor):
            depth -= 1
            cursor += 2
        else:
            cursor += 1
    return cursor


def _extended_regex_hash_count_at(source: str, index: int) -> int | None:
    cursor = index
    while cursor < len(source) and source[cursor] == "#":
        cursor += 1
    hash_count = cursor - index
    if hash_count == 0 or cursor >= len(source) or source[cursor] != "/":
        return None
    return hash_count


def _scan_extended_regex(source: str, start: int) -> int:
    hash_count = _extended_regex_hash_count_at(source, start)
    if hash_count is None:
        return start + 1
    cursor = start + hash_count + 1
    close_delimiter = "/" + ("#" * hash_count)
    interpolation_delimiter = "\\" + ("#" * hash_count) + "("

    while cursor < len(source):
        if source.startswith(close_delimiter, cursor):
            return cursor + len(close_delimiter)
        if source.startswith(interpolation_delimiter, cursor):
            cursor = _skip_interpolation(source, cursor + len(interpolation_delimiter))
            continue
        if source[cursor] == "\\":
            cursor += min(2, len(source) - cursor)
            continue
        cursor += 1
    return len(source)


_STANDARD_REGEX_PREFIX_KEYWORDS = {
    "await",
    "case",
    "else",
    "guard",
    "if",
    "in",
    "return",
    "switch",
    "throw",
    "try",
    "where",
    "while",
    "yield",
}


def _standard_regex_can_start_at(
    source: str,
    index: int,
    *,
    mask: list[str] | None = None,
) -> bool:
    """Recognize expression-position bare-slash regex delimiters.

    Swift's parser disambiguates ``/.../`` from division contextually. Source
    discovery only needs the conservative expression-start cases used by regex
    literals; treating a slash after a value as division prevents an operator
    from masking later accessibility strings.
    """

    if index >= len(source) or source[index] != "/":
        return False
    if index + 1 >= len(source) or source[index + 1] in {"/", "*", "=", "\n", "\r"}:
        return False

    code = mask if mask is not None else source
    cursor = index - 1
    while cursor >= 0 and code[cursor].isspace():
        cursor -= 1
    if cursor < 0:
        return True

    if code[cursor] in "=([{,:;!?&|^~<>+-*%":
        return True

    if code[cursor].isalnum() or code[cursor] == "_":
        end = cursor + 1
        while cursor >= 0 and (code[cursor].isalnum() or code[cursor] == "_"):
            cursor -= 1
        return "".join(code[cursor + 1 : end]) in _STANDARD_REGEX_PREFIX_KEYWORDS

    return False


def _scan_standard_regex(source: str, start: int) -> int | None:
    cursor = start + 1
    in_character_class = False

    while cursor < len(source):
        character = source[cursor]
        if character in {"\n", "\r"}:
            return None
        if character == "\\":
            if source.startswith("\\(", cursor):
                cursor = _skip_interpolation(source, cursor + 2)
            else:
                cursor = min(len(source), cursor + 2)
            continue
        if character == "[":
            in_character_class = True
            cursor += 1
            continue
        if character == "]" and in_character_class:
            in_character_class = False
            cursor += 1
            continue
        if character == "/" and not in_character_class:
            return cursor + 1
        cursor += 1

    return None


def _scan_string(source: str, start: int) -> SourceString:
    delimiter = _string_delimiter_at(source, start)
    if delimiter is None:
        raise ValueError(f"expected string delimiter at offset {start}")
    hash_count, quote_count, quote_start = delimiter
    content_start = quote_start + quote_count
    close_delimiter = ('"' * quote_count) + ("#" * hash_count)
    interpolation_delimiter = "\\" + ("#" * hash_count) + "("
    escape_delimiter = "\\" + ("#" * hash_count)
    interpolation_spans: list[tuple[int, int]] = []
    cursor = content_start

    while cursor < len(source):
        if source.startswith(close_delimiter, cursor):
            return SourceString(
                start=start,
                content_start=content_start,
                content_end=cursor,
                end=cursor + len(close_delimiter),
                interpolation_spans=tuple(interpolation_spans),
            )
        if source.startswith(interpolation_delimiter, cursor):
            expression_start = cursor + len(interpolation_delimiter)
            interpolation_end = _skip_interpolation(source, expression_start)
            interpolation_spans.append((expression_start, interpolation_end))
            cursor = interpolation_end
            continue
        if source.startswith(escape_delimiter, cursor):
            escaped_start = cursor + len(escape_delimiter)
            if escaped_start < len(source):
                escaped_length = (
                    quote_count
                    if source.startswith('"' * quote_count, escaped_start)
                    else 1
                )
                cursor = min(len(source), escaped_start + escaped_length)
                continue
        if source[cursor] == "\\":
            cursor += 1
            continue
        cursor += 1

    return SourceString(
        start=start,
        content_start=content_start,
        content_end=len(source),
        end=len(source),
        interpolation_spans=tuple(interpolation_spans),
    )


def _skip_interpolation(source: str, index: int) -> int:
    depth = 1
    cursor = index
    while cursor < len(source) and depth:
        if source.startswith("//", cursor):
            newline = source.find("\n", cursor + 2)
            cursor = len(source) if newline < 0 else newline + 1
            continue
        if source.startswith("/*", cursor):
            cursor = _skip_block_comment(source, cursor)
            continue
        if _string_delimiter_at(source, cursor) is not None:
            cursor = _scan_string(source, cursor).end
            continue
        if _extended_regex_hash_count_at(source, cursor) is not None:
            cursor = _scan_extended_regex(source, cursor)
            continue
        if _standard_regex_can_start_at(source, cursor):
            regex_end = _scan_standard_regex(source, cursor)
            if regex_end is not None:
                cursor = regex_end
                continue
        if source[cursor] == "(":
            depth += 1
        elif source[cursor] == ")":
            depth -= 1
        cursor += 1
    return cursor


def _mask_range(mask: list[str], source: str, start: int, end: int) -> None:
    for index in range(start, end):
        if source[index] != "\n":
            mask[index] = " "


def _lex_source(source: str) -> tuple[str, list[SourceString]]:
    """Return a code-only mask plus literal string tokens with stable offsets."""

    mask = list(source)
    strings: list[SourceString] = []
    cursor = 0
    while cursor < len(source):
        if source.startswith("//", cursor):
            newline = source.find("\n", cursor + 2)
            end = len(source) if newline < 0 else newline
            _mask_range(mask, source, cursor, end)
            cursor = end
            continue
        if source.startswith("/*", cursor):
            end = _skip_block_comment(source, cursor)
            _mask_range(mask, source, cursor, end)
            cursor = end
            continue
        if _string_delimiter_at(source, cursor) is not None:
            token = _scan_string(source, cursor)
            strings.append(token)
            _mask_range(mask, source, token.start, token.end)
            cursor = token.end
            continue
        if _extended_regex_hash_count_at(source, cursor) is not None:
            end = _scan_extended_regex(source, cursor)
            _mask_range(mask, source, cursor, end)
            cursor = end
            continue
        if _standard_regex_can_start_at(source, cursor, mask=mask):
            end = _scan_standard_regex(source, cursor)
            if end is not None:
                _mask_range(mask, source, cursor, end)
                cursor = end
                continue
        cursor += 1
    return "".join(mask), strings


def _accessibility_literal_values_by_property(
    source: str,
    property_names: tuple[str, ...],
) -> dict[str, set[str]]:
    """Collect accessibility literals in one linear lexical pass."""

    code_mask, strings = _lex_source(source)
    patterns = {
        property_name: (
            re.compile(rf"\.{property_name}\(\s*$"),
            re.compile(rf"\b{property_name}\s*=\s*@?\s*$"),
            re.compile(
                rf"\bset{property_name[0].upper() + property_name[1:]}\s*:\s*@?\s*$"
            ),
        )
        for property_name in property_names
    }
    values = {property_name: set() for property_name in property_names}
    swift_suffix = re.compile(r"\s*\)")
    setter_suffix = re.compile(r"\s*\]")
    previous_token_end = 0

    for token_index, token in enumerate(strings):
        next_token_start = (
            strings[token_index + 1].start
            if token_index + 1 < len(strings)
            else len(code_mask)
        )
        if token.interpolation_spans:
            previous_token_end = token.end
            continue
        prefix = code_mask[previous_token_end : token.start]
        line_end = code_mask.find("\n", token.end, next_token_start)
        if line_end < 0:
            line_end = next_token_start
        assignment_tail = code_mask[token.end : line_end].strip()
        value = source[token.content_start : token.content_end]

        for property_name, (swift_prefix, assignment_prefix, setter_prefix) in patterns.items():
            is_literal_assignment = False
            if swift_prefix.search(prefix):
                is_literal_assignment = (
                    swift_suffix.match(code_mask, token.end, next_token_start) is not None
                )
            elif assignment_prefix.search(prefix):
                is_literal_assignment = assignment_tail in {"", ";"}
            elif setter_prefix.search(prefix):
                is_literal_assignment = (
                    setter_suffix.match(code_mask, token.end, next_token_start) is not None
                )

            if is_literal_assignment and value:
                values[property_name].add(value)

        previous_token_end = token.end

    return values


def _accessibility_literal_values(source: str, property_name: str) -> set[str]:
    return _accessibility_literal_values_by_property(source, (property_name,))[property_name]


def _read_source(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def collect_accessibility_ids(repo_root: Path) -> set[str]:
    identifiers: set[str] = set()

    for path in iter_source_files(repo_root):
        values = _accessibility_literal_values_by_property(
            _read_source(path),
            ("accessibilityIdentifier",),
        )
        identifiers.update(values["accessibilityIdentifier"])

    return identifiers


def collect_accessibility_strings(repo_root: Path) -> tuple[list[str], list[str]]:
    identifiers: set[str] = set()
    labels: set[str] = set()

    for path in iter_source_files(repo_root):
        content = _read_source(path)
        values = _accessibility_literal_values_by_property(
            content,
            ("accessibilityIdentifier", "accessibilityLabel"),
        )
        identifiers.update(values["accessibilityIdentifier"])
        labels.update(values["accessibilityLabel"])

    return sorted(identifiers), sorted(labels)


def collect_launch_hints(repo_root: Path) -> tuple[list[str], list[str]]:
    environment_keys: set[str] = set()
    launch_arguments: set[str] = set()

    for path in iter_source_files(repo_root):
        content = _read_source(path)
        _, strings = _lex_source(content)
        string_values = [
            content[token.content_start : token.content_end]
            for token in strings
            if not token.interpolation_spans
        ]
        environment_keys.update(
            key
            for key in string_values
            if ENV_KEY_PATTERN.fullmatch(key)
            if "AUTOMATION" in key
            or "UITEST" in key
            or "UI_TEST" in key
            or key.endswith("_TESTING")
        )
        launch_arguments.update(
            value for value in string_values if LAUNCH_ARGUMENT_PATTERN.fullmatch(value)
        )

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


def _is_finite_number(value: Any) -> bool:
    if not _is_number(value):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_screenshot_output(output: str, *, step_index: int) -> None:
    posix_path = PurePosixPath(output)
    windows_path = PureWindowsPath(output)
    if posix_path.is_absolute() or windows_path.is_absolute():
        raise ScenarioContractError(
            f"Scenario step {step_index} screenshot output must be a relative path inside the artifacts directory"
        )

    if posix_path == PurePosixPath(".") or windows_path == PureWindowsPath("."):
        raise ScenarioContractError(
            f"Scenario step {step_index} screenshot output must name a file inside the artifacts directory"
        )

    parts = (*posix_path.parts, *windows_path.parts)
    if ".." in parts:
        raise ScenarioContractError(
            f"Scenario step {step_index} screenshot output cannot contain parent-directory traversal"
        )


ACTION_STEP_FIELDS: dict[str, set[str]] = {
    "launch": {"action", "arguments", "environment", "wait_seconds"},
    "tap": {"action", "id", "label", "timeout"},
    "type": {"action", "id", "label", "text", "timeout"},
    "wait": {"action", "seconds"},
    "assertVisible": {"action", "id", "label", "timeout"},
    "assertText": {"action", "id", "label", "text", "timeout"},
    "screenshot": {"action", "output"},
}


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
    if not _is_nonempty_string(name):
        raise ScenarioContractError("Scenario payload must contain a non-empty string 'name'")

    description = payload.get("description")
    if description is not None and not isinstance(description, str):
        raise ScenarioContractError("Scenario payload 'description' must be a string when provided")

    steps = payload.get("steps")
    if not isinstance(steps, list):
        raise ScenarioContractError("Scenario payload must contain a 'steps' array")
    if not steps:
        raise ScenarioContractError("Scenario payload 'steps' array cannot be empty")

    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ScenarioContractError(f"Scenario step {index} must be an object")

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

        extra_step_fields = sorted(set(step.keys()) - ACTION_STEP_FIELDS[action])
        if extra_step_fields:
            raise ScenarioContractError(
                f"Scenario step {index} action '{action}' contains unsupported fields: "
                f"{', '.join(extra_step_fields)}"
            )

        for key in ("id", "label", "text", "output"):
            if key not in step:
                continue
            value = step[key]
            if not isinstance(value, str):
                raise ScenarioContractError(
                    f"Scenario step {index} field '{key}' must be a string when provided"
                )
            if not value.strip():
                raise ScenarioContractError(
                    f"Scenario step {index} field '{key}' must be non-empty when provided"
                )

        for key in ("seconds", "wait_seconds", "timeout"):
            if key not in step:
                continue
            value = step[key]
            if not _is_finite_number(value):
                raise ScenarioContractError(
                    f"Scenario step {index} field '{key}' must be a finite number when provided"
                )
            if key == "timeout" and value <= 0:
                raise ScenarioContractError(
                    f"Scenario step {index} field 'timeout' must be greater than zero"
                )
            if key != "timeout" and value < 0:
                raise ScenarioContractError(
                    f"Scenario step {index} field '{key}' cannot be negative"
                )

        if action in {"tap", "assertVisible"} and not (
            _is_nonempty_string(step.get("id")) or _is_nonempty_string(step.get("label"))
        ):
            raise ScenarioContractError(
                f"Scenario step {index} action '{action}' requires a non-empty 'id' or 'label'"
            )

        if action in {"type", "assertText"} and not _is_nonempty_string(step.get("text")):
            raise ScenarioContractError(
                f"Scenario step {index} action '{action}' requires non-empty 'text'"
            )

        if action == "wait" and "seconds" not in step:
            raise ScenarioContractError(
                f"Scenario step {index} action 'wait' requires nonnegative 'seconds'"
            )

        if "arguments" in step:
            arguments = step["arguments"]
            if not isinstance(arguments, list) or not all(isinstance(item, str) for item in arguments):
                raise ScenarioContractError(
                    f"Scenario step {index} field 'arguments' must be an array of strings when provided"
                )

        if "environment" in step:
            environment = step["environment"]
            if not isinstance(environment, dict):
                raise ScenarioContractError(
                    f"Scenario step {index} field 'environment' must be an object when provided"
                )
            for env_key, env_value in environment.items():
                if not isinstance(env_key, str) or not isinstance(env_value, str):
                    raise ScenarioContractError(
                        f"Scenario step {index} field 'environment' must contain only string keys and values"
                    )
                if not env_key.strip():
                    raise ScenarioContractError(
                        f"Scenario step {index} field 'environment' cannot contain an empty key"
                    )

        output = step.get("output")
        if action == "screenshot" and isinstance(output, str):
            _validate_screenshot_output(output, step_index=index)


def normalize_openai_planner_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert the strict OpenAI wire shape into the provider-neutral runtime shape."""

    if not isinstance(payload, dict):
        raise ScenarioContractError("Planner payload must be a JSON object")

    normalized: dict[str, Any] = {
        "name": payload.get("name"),
        "steps": [],
    }
    if payload.get("description") is not None:
        normalized["description"] = payload.get("description")

    steps = payload.get("steps")
    if not isinstance(steps, list):
        raise ScenarioContractError("Planner payload must contain a 'steps' array")

    optional_step_fields = (
        "id",
        "label",
        "text",
        "output",
        "seconds",
        "wait_seconds",
        "timeout",
        "arguments",
    )
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ScenarioContractError(f"Planner step {index} must be an object")

        normalized_step: dict[str, Any] = {"action": step.get("action")}
        for key in optional_step_fields:
            if step.get(key) is not None:
                normalized_step[key] = step[key]

        environment_pairs = step.get("environment")
        if environment_pairs is not None:
            if not isinstance(environment_pairs, list):
                raise ScenarioContractError(
                    f"Planner step {index} field 'environment' must be an array of key/value objects or null"
                )

            environment: dict[str, str] = {}
            for pair_index, pair in enumerate(environment_pairs):
                if not isinstance(pair, dict) or set(pair) != {"key", "value"}:
                    raise ScenarioContractError(
                        f"Planner step {index} environment entry {pair_index} must contain exactly 'key' and 'value'"
                    )
                key = pair.get("key")
                value = pair.get("value")
                if not _is_nonempty_string(key) or not isinstance(value, str):
                    raise ScenarioContractError(
                        f"Planner step {index} environment entry {pair_index} must contain a non-empty string key and string value"
                    )
                if key in environment:
                    raise ScenarioContractError(
                        f"Planner step {index} environment contains duplicate key '{key}'"
                    )
                environment[key] = value
            normalized_step["environment"] = environment

        normalized["steps"].append(normalized_step)

    validate_scenario_payload(normalized)
    return normalized


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
