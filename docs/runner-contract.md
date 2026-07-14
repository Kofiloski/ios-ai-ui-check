---
summary: Contract for the app-specific runner script that executes scenarios inside the app repo.
read_when:
  - implementing a runner for a new iOS app
  - changing scenario shape or environment variables passed to repo-local runners
---

# Runner Contract

The runner is provided by the app repo. The public action will invoke it after resolving the scenario and booting the target simulator.

If you use [`scripts/scaffold-app-repo.py`](../scripts/scaffold-app-repo.py), this contract is already bootstrapped for you through a generated `XCUITest` target and a thin shell runner.

## Environment Variables

The action exports:

- `AI_UI_SCENARIO_PATH`
- `AI_UI_ARTIFACTS_DIR`
- `AI_UI_EXPECTED_SCREENSHOT_PATH`
- `AI_UI_PLANNER_GOAL`
- `AI_UI_PLANNER_NOTE_PATH`: optional path to a short planner-generated markdown note that explains a safer narrowed route
- `AI_UI_SIMULATOR_NAME`
- `AI_UI_SIMULATOR_RUNTIME`
- `AI_UI_SIMULATOR_UDID`
- `AI_UI_SIMULATOR_RUNTIME_NAME`
- `AI_UI_MAX_DURATION_SECONDS`: timeout for the current runner invocation; the public `max-duration-seconds` input applies the same limit independently to inspection, planning, and final scenario execution

When the action uses AI planning, it may also invoke the runner in `inspect` mode before planning. In that mode the scaffolded runner writes:

- `AI_UI_BEFORE_PLANNING_UI_TREE_PATH`
- `AI_UI_BEFORE_PLANNING_SCREENSHOT_PATH`

For compatibility with older scaffolded repos, the public action also still sets deprecated aliases `AI_UI_CURRENT_UI_TREE_PATH` and `AI_UI_CURRENT_SCREENSHOT_PATH` to the same values.

## Responsibilities

The runner should:

- support normal scenario execution
- optionally support `inspect` mode that launches the app and exports a live hierarchy snapshot plus screenshot
- prepare test data or mock state
- install or launch the app
- execute the scenario steps
- fail with a non-zero exit code on assertion failure
- write a human-readable `summary.md` into `AI_UI_ARTIFACTS_DIR`

The public action will upload the artifacts directory. The runner should save any meaningful app-specific screenshots into that directory when needed.
When `AI_UI_PLANNER_GOAL` is present, the public action and generated runner preserve that exact text in `summary.md` so artifact consumers and PR comments can see the original requested flow.
When `AI_UI_PLANNER_NOTE_PATH` is present and points to a note file, the public action and generated runner append that note to `summary.md`.
If planning fails before the runner starts, the public action writes `summary.md` itself together with planner-side debugging artifacts and does not invoke the runner at all.
The public action also writes `manifest.json` into the artifact root after planning or runner execution so downstream tooling can discover artifact paths without scraping markdown summaries.

## Execution Model

Repo-local runners should treat the scenario as declarative input. Avoid embedding app-specific test logic into the action repo.

The scaffolded runner supports two modes:

- default execution mode: run the resolved scenario
- `inspect` mode: launch the app, export `before-planning-ui-tree.json`, and capture `before-planning-screenshot.png`

`before-planning-screenshot.png` is the pre-planning screenshot from `inspect` mode. It shows the live UI state the planner saw before generating the scenario, so treat it as planning/debug context rather than a result screenshot.
The scaffolded `before-planning-ui-tree.json` is a debugging-oriented hierarchy snapshot derived from XCTest. Use it to improve AI planning context, not as a stable oracle for pass/fail assertions.
For the scaffolded runner, `inspect` mode is only considered successful when it produces both files.
When the scaffolded runner attaches XCTest's `Failure Screenshot`, the public action extracts that attachment from `.xcresult` into `failure-screenshot.png` in the artifacts directory when available.

Recommended executor strategies:

- `XCUITest` as the primary driver
- deep links or launch arguments for deterministic state setup
- stable accessibility identifiers for all tappable or asserted UI

The scaffolded baseline runner supports these step actions:

- `launch`
- `tap`
- `type`
- `wait`
- `assertVisible`
- `assertText`
- `screenshot`

## Scenario Validation

Every runtime scenario must have a nonblank `name` and a nonempty `steps` array. Unknown top-level fields, unknown step fields, and fields that do not apply to a step's action are rejected before the runner starts.

Supported step shapes are:

- `launch`: optional `arguments`, `environment`, and `wait_seconds`
- `tap`: `id` or `label` is required; optional `timeout`
- `type`: nonblank `text` is required; optional `id`, `label`, and `timeout`; without a target, the runner types into the app
- `wait`: finite, nonnegative `seconds` is required
- `assertVisible`: `id` or `label` is required; optional `timeout`
- `assertText`: nonblank `text` is required; optional `id`, `label`, and `timeout`; without a target, the runner searches the visible app hierarchy
- `screenshot`: optional relative `output`; absolute paths, parent-directory traversal, and paths resolving to the artifacts directory itself are rejected so output names a file under `AI_UI_ARTIFACTS_DIR`

`wait_seconds` must also be finite and nonnegative. Every provided `timeout` must be finite and greater than zero.

The scaffolded OpenAI planner uses a separate strict wire schema whose launch environment is an array of `{ "key", "value" }` entries. The planner normalizes and validates that response before writing the provider-neutral runtime scenario, so app-side runners continue to receive `environment` as a string-to-string JSON object.

## Suggested Summary Format

Write `summary.md` in flat markdown. Example:

```md
## iOS AI UI Check

- Scenario: Verify detail screen
- Result: passed
- Notes: Opened the detail screen and validated the title plus header image visibility.
```

If `AI_UI_PLANNER_GOAL` is set, it is reasonable to include a dedicated `Planner Goal` section or let the public action append one after runner execution.
