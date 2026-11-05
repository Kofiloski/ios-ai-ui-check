---
summary: Reference for action inputs, outputs, planner environment, and scenario JSON.
read_when:
  - Looking up an action or reusable-workflow setting
  - Implementing a custom planner or inspecting scenario JSON
---

# Action reference

The executable contract is [action.yml](../action.yml). For complete caller workflows, see [integration patterns](integration-patterns.md) and [examples](../examples/README.md).

## Inputs

`planner-command` is required when no provided scenario is selected. All other inputs are optional.

| Input | Default | Purpose |
| --- | --- | --- |
| `simulator-name` | `iPhone 17 Pro` | Target simulator device name. |
| `simulator-runtime` | `26.2` | Target iOS Simulator runtime version, for example 26.2. |
| `provided-scenario-path` | Empty | Path to a checked-in scenario JSON file; bypasses planning when set. |
| `planner-command` | Empty | Command that writes scenario JSON to AI_UI_SCENARIO_OUTPUT_PATH when no provided scenario is set. |
| `planner-provider` | Empty | Optional provider forwarded to the app-owned planner (openai, anthropic, or openai-compatible in the scaffold). |
| `planner-model` | Empty | Optional model ID forwarded to the app-owned planner. |
| `planner-effort` | Empty | Optional reasoning effort forwarded unchanged to the app-owned planner. |
| `planner-base-url` | Empty | Optional API base URL for the scaffolded openai-compatible planner. |
| `planner-goal` | Empty | Optional goal sentence forwarded to the app-owned planner command. |
| `base-ref` | Empty | Explicit comparison base ref; requires head-ref and locally available history. |
| `head-ref` | Empty | Explicit comparison head ref; must match the checked-out HEAD. |
| `release-notes-path` | Empty | Optional UTF-8 release notes file; requires explicit base-ref and head-ref. |
| `expected-screenshot-path` | Empty | Optional reference screenshot forwarded to the planner and runner; no built-in image diff is performed. |
| `artifacts-dir` | `artifacts/ios-ai-ui-check` | Directory for summaries, manifests, media, logs, screenshots, and result bundles. |
| `upload-artifacts` | `true` | Upload the artifacts directory even when planning or execution fails. |
| `record-video` | `true` | Record Simulator video while the app-owned runner executes. |
| `comment-on-pr` | `true` | Create or update one managed summary comment on pull_request events. |
| `github-token` | Empty | Token used only to create or update the managed pull request comment. |
| `comment-author-login` | Empty | GitHub login that owns the managed PR comment; set this when github-token posts as a custom user or bot. |
| `max-duration-seconds` | `300` | Timeout applied independently to inspection, planner, and final runner commands. |

The comment token falls back to the inherited token or current workflow token when `github-token` is empty. The effective comment author defaults to `github-actions[bot]`; set `comment-author-login` when a custom token posts as another user or bot so reruns update the same comment.

## Outputs

| Output | Meaning |
| --- | --- |
| `status` | passed or failed |
| `resolved-source` | provided or ai when scenario resolution succeeded |
| `failure-note` | High-level failure note when planning or runner execution failed |
| `scenario-path` | Resolved scenario path |
| `summary-path` | Markdown summary path |
| `video-path` | Video path when recording is enabled and a video file was captured |
| `artifact-url` | Uploaded artifact URL when available |
| `before-planning-ui-tree-path` | UI tree path captured before AI planning when available |
| `before-planning-screenshot-path` | Screenshot path captured before AI planning when available |
| `current-ui-tree-path` | Deprecated alias for before-planning-ui-tree-path |
| `current-screenshot-path` | Deprecated alias for before-planning-screenshot-path |
| `planner-note-path` | Planner note path when AI planning emitted a note about a narrowed or safer route |
| `planner-request-path` | Planner request summary path when AI planning is attempted |
| `planner-response-path` | Planner response artifact path, preferring planner-response.json over planner-response.txt |
| `planner-validation-error-path` | Planner validation error path when AI planning produced an invalid or risky scenario |
| `planner-summary-path` | Planner summary path when AI planning is attempted |
| `artifact-manifest-path` | Machine-readable manifest of uploaded artifacts |

`video-path` is populated only when recording is enabled and a nonempty video finalized successfully. Capture failures are reported without replacing the UI-check result. Optional artifact paths are populated only when that evidence exists; use the artifact manifest rather than assuming every file was produced.

## Scenario Format

Example shape for the scaffolded `XCUITest` runner. Replace the sample launch flags and identifiers with values actually supported by the app:

```json
{
  "name": "Verify detail screen",
  "description": "Launch the app into a known route and validate the primary content.",
  "steps": [
    {
      "action": "launch",
      "wait_seconds": 2,
      "environment": {
        "APP_AUTOMATION": "1",
        "APP_AUTOMATION_ROUTE": "detail"
      }
    },
    { "action": "tap", "id": "item_card_primary" },
    { "action": "assertText", "text": "Primary Item" },
    { "action": "assertVisible", "id": "detail_header_image" },
    { "action": "screenshot", "output": "detail-screen.png" }
  ]
}
```

The action and the scaffolded planner now share one canonical scenario contract from `scripts/ai_ui_contract.py`, and [schemas/scenario.schema.json](../schemas/scenario.schema.json) is the generated JSON copy of that same contract. The scaffolded runner understands `launch`, `tap`, `type`, `wait`, `assertVisible`, `assertText`, and `screenshot`. App-specific runners can support more, but the public action and generated planner only rely on the shared contract above.

## Planner command environment

When the action falls back to AI planning, it runs the planner command and expects it to write scenario JSON to `AI_UI_SCENARIO_OUTPUT_PATH`.

The action also exports:

- `AI_UI_EXPECTED_SCREENSHOT_PATH`
- `AI_UI_BEFORE_PLANNING_SCREENSHOT_PATH`
- `AI_UI_BEFORE_PLANNING_UI_TREE_PATH`
- `AI_UI_PLANNER_NOTE_OUTPUT_PATH`: optional sidecar path that a planner command can write with a short markdown note explaining why it narrowed the requested goal into a safer route
- `AI_UI_EVENT_PATH`
- `AI_UI_REPOSITORY`
- `AI_UI_WORKSPACE`

For compatibility with older scaffolded app repos, the action still exports deprecated aliases `AI_UI_CURRENT_SCREENSHOT_PATH` and `AI_UI_CURRENT_UI_TREE_PATH` with the same values.

Provider settings, API credentials, and model-specific effort behavior are documented in [planner configuration](planner-configuration.md). Custom planners still write the same validated runtime scenario. The canonical schema, supported step shapes, and XCTest selector override are described in the [runner contract](runner-contract.md).

## Reusable Workflow Wrapper

This repo also includes [`.github/workflows/run.yml`](../.github/workflows/run.yml).

Use it when you want to configure the macOS runner as an input. The wrapper defaults to `runs-on: macos-26` and:

- accepts the core action inputs, including simulator, artifact, video, and timeout controls
- checks out the caller repository
- checks out the action repository
- optionally exports a generic planner API key secret into the planner command environment through `planner-api-key` plus `planner-api-key-env-name`
- forwards the same outputs as the core action, including `artifact-manifest-path`
- invokes the same local action

Use the core action directly when you want to plug into an existing job. Use the reusable workflow when you want the action to own the job.

## Pull request comments

When GitHub restricts the default token on fork or Dependabot pull requests, the optional managed comment is skipped without failing the UI check. Artifacts and the job summary still carry the evidence. A caller-provided writable `github-token` remains supported.
