#!/usr/bin/env bash
__SCAFFOLD_HEADER_SHELL__
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_SCENARIO_RELATIVE_PATH=__SCENARIO_PATH_SHELL__
OUTPUT_PATH="${AI_UI_SCENARIO_OUTPUT_PATH:?AI_UI_SCENARIO_OUTPUT_PATH is required}"
OPENAI_API_KEY="${OPENAI_API_KEY:?OPENAI_API_KEY is required}"
OPENAI_MODEL="${AI_UI_PLANNER_MODEL:-${AI_UI_OPENAI_MODEL:-gpt-5-mini}}"
EXPECTED_SCREENSHOT_PATH="${AI_UI_EXPECTED_SCREENSHOT_PATH:-}"
PLANNER_CONTEXT_PATH="${AI_UI_PLANNER_CONTEXT_PATH:-$ROOT_DIR/.github/ai-ui/planner-context.md}"
SCENARIO_EXAMPLE_PATH="${AI_UI_SCENARIO_EXAMPLE_PATH:-$ROOT_DIR/$DEFAULT_SCENARIO_RELATIVE_PATH}"

mkdir -p "$(dirname "$OUTPUT_PATH")"

python3 - "$ROOT_DIR" "$OUTPUT_PATH" "$OPENAI_MODEL" "$EXPECTED_SCREENSHOT_PATH" "$PLANNER_CONTEXT_PATH" "$SCENARIO_EXAMPLE_PATH" <<'PY'
import base64
import json
import mimetypes
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

root_dir = Path(sys.argv[1])
output_path = Path(sys.argv[2])
model = sys.argv[3]
expected_screenshot_path = Path(sys.argv[4]) if sys.argv[4] else None
planner_context_path = Path(sys.argv[5])
scenario_example_path = Path(sys.argv[6])
api_key = os.environ["OPENAI_API_KEY"]
repository = os.environ.get("AI_UI_REPOSITORY", "")
planner_goal = os.environ.get("AI_UI_PLANNER_GOAL", "").strip()
app_scheme = __SCHEME_PYTHON__


def optional_path(*environment_names: str) -> Path | None:
    for environment_name in environment_names:
        raw_value = os.environ.get(environment_name, "").strip()
        if raw_value:
            return Path(raw_value)
    return None


event_path = optional_path("AI_UI_EVENT_PATH")
before_planning_screenshot_path = optional_path(
    "AI_UI_BEFORE_PLANNING_SCREENSHOT_PATH",
    "AI_UI_CURRENT_SCREENSHOT_PATH",
)
before_planning_ui_tree_path = optional_path(
    "AI_UI_BEFORE_PLANNING_UI_TREE_PATH",
    "AI_UI_CURRENT_UI_TREE_PATH",
)
planner_note_output_path = optional_path("AI_UI_PLANNER_NOTE_OUTPUT_PATH")
planner_draft_scenario_path_raw = os.environ.get("AI_UI_PLANNER_DRAFT_SCENARIO_PATH", "").strip()
planner_draft_scenario_path = Path(planner_draft_scenario_path_raw) if planner_draft_scenario_path_raw else None

sys.path.insert(0, str(root_dir / "scripts"))

from ai_ui_contract import (  # noqa: E402
    OPENAI_PLANNER_SCHEMA,
    collect_accessibility_strings,
    collect_launch_hints,
    collect_ui_tree_identifiers,
    normalize_openai_planner_scenario,
    read_json,
    read_text,
    render_markdown_list,
    summarize_ui_tree,
    validate_generated_scenario,
    write_json,
)


def collect_git_diff(repo_root: Path, payload: dict) -> str:
    pr = payload.get("pull_request") or {}
    head_sha = ((pr.get("head") or {}).get("sha") or "").strip()
    base_sha = ((pr.get("base") or {}).get("sha") or "").strip()
    candidates: list[list[str]] = []

    if base_sha and head_sha:
        candidates.append(["git", "-C", str(repo_root), "diff", "--unified=0", "--no-color", f"{base_sha}...{head_sha}"])
    candidates.append(["git", "-C", str(repo_root), "diff", "--unified=0", "--no-color", "HEAD^", "HEAD"])

    for command in candidates:
        try:
            completed = subprocess.run(command, check=True, capture_output=True, text=True)
        except Exception:
            continue
        diff_text = completed.stdout.strip()
        if diff_text:
            return diff_text[:20000]

    return ""


def load_event_payload(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def build_image_content(path: Path) -> dict | None:
    if not path.is_file():
        return None
    media_type, _ = mimetypes.guess_type(path.name)
    if not media_type:
        media_type = "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "input_image",
        "image_url": f"data:{media_type};base64,{encoded}",
    }

def scenario_text_blob(scenario: dict) -> str:
    parts: list[str] = []
    for key in ("name", "description"):
        value = scenario.get(key)
        if isinstance(value, str) and value:
            parts.append(value)

    for step in scenario.get("steps", []):
        if not isinstance(step, dict):
            continue
        for key in ("action", "id", "label", "text", "output"):
            value = step.get(key)
            if isinstance(value, str) and value:
                parts.append(value)

    return "\n".join(parts).lower()


def derive_planner_note(
    *,
    planner_goal: str,
    scenario: dict,
    before_planning_ui_tree_identifiers: set[str],
) -> str:
    goal = planner_goal.strip().lower()
    if not goal:
        return ""

    scenario_blob = scenario_text_blob(scenario)
    requested_conditional_states = []
    conditional_hints = {
        "empty state": ("empty state", "empty-state"),
        "paywall": ("paywall",),
        "sheet": ("sheet",),
        "modal": ("modal",),
        "draft": ("draft",),
        "processing": ("processing",),
    }

    for label, patterns in conditional_hints.items():
        if any(pattern in goal for pattern in patterns):
            requested_conditional_states.append((label, patterns))

    if not requested_conditional_states:
        return ""

    unmet_labels = [
        label
        for label, patterns in requested_conditional_states
        if not any(pattern in scenario_blob for pattern in patterns)
    ]
    if not unmet_labels:
        return ""

    scenario_ids = {
        step.get("id")
        for step in scenario.get("steps", [])
        if isinstance(step, dict) and isinstance(step.get("id"), str) and step.get("id")
    }
    used_observed_ui = bool(scenario_ids & before_planning_ui_tree_identifiers)
    unmet_text = ", ".join(unmet_labels)
    if used_observed_ui:
        return (
            f"The requested goal mentioned `{unmet_text}`, but the planner used a safer path from the observed before-planning UI "
            "because that conditional state was not guaranteed by the available launch context."
        )

    return (
        f"The requested goal mentioned `{unmet_text}`, but the planner used a safer deterministic path "
        "because that conditional state was not guaranteed by the available launch context."
    )


event_payload = load_event_payload(event_path)
pr = event_payload.get("pull_request") or {}
pr_title = (pr.get("title") or "").strip()
pr_body = (pr.get("body") or "").strip()
resolved_goal = planner_goal
if not resolved_goal and pr:
    resolved_goal = "Verify the most likely user-visible flow affected by this pull request."
planner_context = read_text(planner_context_path, fallback="No planner context file was provided.")
scenario_example = read_text(scenario_example_path, fallback="")
identifiers, labels = collect_accessibility_strings(root_dir)
launch_environment_keys, launch_arguments = collect_launch_hints(root_dir)
git_diff = collect_git_diff(root_dir, event_payload)
before_planning_ui_tree_summary = (
    summarize_ui_tree(before_planning_ui_tree_path)
    if before_planning_ui_tree_path is not None
    else "(unavailable)"
)
before_planning_ui_tree_identifiers = (
    collect_ui_tree_identifiers(before_planning_ui_tree_path)
    if before_planning_ui_tree_path is not None
    else set()
)

system_prompt = (
    "You generate deterministic iOS UI test scenarios for a constrained XCUITest runner. "
    "Return only JSON that matches the provided schema. "
    "The strict response shape requires every step field; set fields that do not apply to null. "
    "Represent launch environment values as an array of key/value objects, or null when unused. "
    "Use only arguments, environment, and wait_seconds for launch; id, label, and timeout for tap or assertVisible; id, label, text, and timeout for type or assertText; seconds for wait; and output for screenshot. "
    "Only use these supported actions: launch, tap, type, wait, assertVisible, assertText, screenshot. "
    "Prefer stable accessibility identifiers over labels. "
    "Always begin with a launch step. "
    "Use a simple happy path that is likely to pass in CI. "
    "When a requested test goal is provided, use it to choose the flow while staying deterministic and conservative. "
    "When pull request metadata and diff are available, bias toward the most likely user-visible flow affected by the change. "
    "Prefer the most specific actionable identifier available for the intended branch of the flow. "
    "If identifiers share a prefix such as foo.add, foo.add.detailed, and foo.add.camera, treat the generic parent as a menu or chooser trigger rather than assuming it opens the final form directly. "
    "Do not synthesize container identifiers by renaming a known suffix. If repo context shows ids ending in list, overview, root, or screen, use those exact ids instead of inventing nearby variants such as form. "
    "Do not invent identifiers that are not present in the provided repo context unless a visible label is a better fallback. "
    "Do not invent launch arguments or environment variables. "
    "Only use launch environment variables when the exact key-value pair is explicitly present in the planner context or checked-in scenario example. "
    "Only use launch arguments when the exact literal is explicitly present in the planner context, checked-in scenario example, or discovered launch arguments list. "
    "Treat source-discovered environment key names as weak hints only, not as usable launch configuration. "
    "Do not target identifiers whose names imply conditional state, such as empty states, sheets, modals, drafts, or paywalls, unless the before-planning UI tree already shows them or the planner context or checked-in scenario example documents how to reach them deterministically. "
    "When both a generic create button and an empty-state create button exist, prefer the generic create button unless launch configuration guarantees the empty state. "
    "If a live UI tree summary is present and usable, prefer reproducing that observed state with empty launch arguments and environment instead of adding automation overrides. "
    "If startup state is not deterministic from the provided context, avoid asserting a guessed root element. "
    "If context is weak, emit a conservative scenario that launches the app, waits briefly, and captures a screenshot."
)

user_prompt = f"""
Repository: {repository or root_dir.name}
App scheme: {app_scheme}

Planner context:
{planner_context}

Pull request title:
{pr_title or '(none)'}

Pull request body:
{pr_body or '(none)'}

Requested test goal:
{resolved_goal or '(not provided)'}

Git diff:
{git_diff or '(unavailable)'}

Before-planning UI tree summary from a live simulator launch:
{before_planning_ui_tree_summary}

Accessibility identifiers discovered in the repo:
{render_markdown_list(identifiers)}

Accessibility labels discovered in the repo:
{render_markdown_list(labels)}

Launch environment keys discovered in the repo (key names only, values unknown):
{render_markdown_list(launch_environment_keys)}

Launch arguments discovered in the repo (concrete literals):
{render_markdown_list(launch_arguments)}

Checked-in scenario example:
{scenario_example or '(none)'}

Produce one scenario JSON object.
Favor deterministic launch environment and stable assertions.
Never use placeholder launch flags like UITESTING or RESET_SEED_DATA unless they appear in the provided context above.
Treat discovered environment keys as key-name hints only. Do not choose a value for one unless the exact key-value pair appears in the planner context or checked-in scenario example.
Only assert a startup root if the launch step makes that root deterministic.
If a before-planning UI tree summary is present, prefer interacting with that live state instead of assuming startup behavior from static code.
If the before-planning UI tree summary already shows a valid starting screen, prefer an empty launch environment and follow that observed screen.
If discovered identifiers suggest a menu tree or chooser, add the intermediate tap for the specific option before asserting the destination form or screen.
Use exact identifier spellings from the provided context. Do not mutate suffixes like list, overview, root, or screen into new names such as form.
Do not use state-dependent identifiers such as empty-state, modal, sheet, draft, or paywall IDs unless the before-planning UI tree already shows them or the planner context or checked-in scenario example explicitly documents that deterministic path.
When both a generic add/create button and an empty-state create button exist, prefer the generic add/create button unless the launch step explicitly guarantees an empty state.
Keep the scenario short, usually 3 to 7 steps.
Add one screenshot step near the end.
"""

content = [{"type": "input_text", "text": user_prompt}]
if before_planning_screenshot_path and before_planning_screenshot_path.exists():
    image_content = build_image_content(before_planning_screenshot_path)
    if image_content is not None:
        content.append(image_content)
if expected_screenshot_path and expected_screenshot_path.exists():
    image_content = build_image_content(expected_screenshot_path)
    if image_content is not None:
        content.append(image_content)

payload = {
    "model": model,
    "instructions": system_prompt,
    "input": [
        {
            "role": "user",
            "content": content,
        }
    ],
    "text": {
        "format": {
            "type": "json_schema",
            "name": "ios_ui_scenario",
            "schema": OPENAI_PLANNER_SCHEMA,
            "strict": True,
        }
    },
}

request = urllib.request.Request(
    "https://api.openai.com/v1/responses",
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    },
    method="POST",
)

try:
    with urllib.request.urlopen(request) as response:
        response_payload = json.loads(response.read().decode("utf-8"))
except urllib.error.HTTPError as exc:
    details = exc.read().decode("utf-8", errors="replace")
    raise SystemExit(f"OpenAI request failed: HTTP {exc.code}\n{details}")

output_text_parts: list[str] = []
for item in response_payload.get("output", []):
    if item.get("type") != "message":
        continue
    for content_item in item.get("content", []):
        if content_item.get("type") == "output_text":
            output_text_parts.append(content_item.get("text", ""))

if not output_text_parts:
    raise SystemExit("OpenAI response did not include output_text content")

planner_scenario = json.loads("".join(output_text_parts))
if planner_draft_scenario_path is not None:
    write_json(planner_draft_scenario_path, planner_scenario)
scenario = normalize_openai_planner_scenario(planner_scenario)
validate_generated_scenario(
    scenario,
    known_identifiers=identifiers,
    before_planning_ui_tree_identifiers=before_planning_ui_tree_identifiers,
    documented_text="\n".join(part for part in (planner_context, scenario_example) if part),
)
write_json(output_path, scenario)

planner_note = derive_planner_note(
    planner_goal=planner_goal,
    scenario=scenario,
    before_planning_ui_tree_identifiers=before_planning_ui_tree_identifiers,
)
if planner_note_output_path is not None and not planner_note_output_path.is_dir():
    planner_note_output_path.parent.mkdir(parents=True, exist_ok=True)
    if planner_note:
        planner_note_output_path.write_text(planner_note + "\n", encoding="utf-8")
    elif planner_note_output_path.exists():
        planner_note_output_path.unlink()
PY
