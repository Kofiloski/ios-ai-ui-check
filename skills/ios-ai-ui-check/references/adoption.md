# Adoption reference

## New app repository

Use a release-pinned checkout of the upstream repository. Replace the project and scheme values with the target app's real shared scheme.

```bash
git clone --branch v0.6.0 --depth 1 \
  https://github.com/Kofiloski/ios-ai-ui-check.git ../ios-ai-ui-check

python3 ../ios-ai-ui-check/scripts/scaffold-app-repo.py \
  --repo-root . \
  --project App.xcodeproj \
  --scheme App \
  --dry-run
```

After reviewing the dry-run, repeat without `--dry-run`. Then review the generated scenario, planner context, launch contract, workflow, and UI-test target before running:

```bash
./scripts/local-ai-ui-check.sh --use-example-scenario
```

## Minimal deterministic PR caller

```yaml
name: iOS UI Check

on:
  workflow_dispatch:
  pull_request:

permissions:
  contents: read
  pull-requests: write

jobs:
  ui-check:
    uses: Kofiloski/ios-ai-ui-check/.github/workflows/run.yml@v0.6.0
    with:
      provided-scenario-path: .github/ai-ui/verify-primary-flow.json
```

This mode does not require a model API key.

## Planner mode

Use planner mode only when the app repository supplies and reviews its own planner command. The reusable action does not call a provider directly.

```yaml
- uses: Kofiloski/ios-ai-ui-check@v0.6.0
  with:
    planner-command: ./scripts/plan-ai-ui-scenario.sh
    planner-provider: anthropic
    planner-model: claude-sonnet-4-6
    planner-effort: high
    planner-goal: Verify the most likely user-visible flow affected by this PR.
```

Supply `ANTHROPIC_API_KEY` in the action step environment, or `planner-api-key` as a reusable-workflow secret. Give the planner only the context needed for the flow. A forked `pull_request` does not receive repository secrets.

## Planner settings

When the user specifies provider, model, and effort, preserve all three. These settings configure planner API calls, not the coding-agent session itself. Check the actual app-owned planner and action revision before configuring them. Version `v0.6.0` adds `planner-provider`, `planner-model`, and `planner-effort` inputs plus local `--provider`, `--model`, and `--effort` flags. Older pins and scaffolds, including `v0.5.0`, do not gain these options by installing this skill; explicitly refresh managed files and use `v0.6.0` or a reviewed newer action revision.

For an updated scaffold with `ANTHROPIC_API_KEY` in the environment:

```bash
./scripts/local-ai-ui-check.sh --provider anthropic --model claude-sonnet-4-6 --effort high --goal "Verify settings persist"
```

The built-in providers are `anthropic`, `openai`, and `openai-compatible`. Native Anthropic planning uses Messages and `output_config.effort`; OpenAI uses Responses and `reasoning.effort`. Compatible endpoints require an explicit base URL and matching image/structured-output/effort capabilities. Use `default` or omit effort to leave the model default intact. Supported levels vary by model; preserve API rejections rather than silently replacing or weakening the requested settings.

`ANTHROPIC_API_KEY` and `OPENAI_API_KEY` are provider-specific. `AI_UI_PLANNER_API_KEY` takes precedence as a generic credential. Never require an OpenAI key for Anthropic or an app-owned replacement planner. Deterministic scenarios require no model key. Provider fixtures do not prove live model access or quality. Full configuration and evidence boundaries: https://github.com/Kofiloski/ios-ai-ui-check/blob/v0.6.0/docs/planner-configuration.md.

## Expected evidence

The artifact bundle can include:

- `summary.md`
- `manifest.json`
- `scenario.json`
- `run.mp4`
- `failure-screenshot.png`
- a UI-test `.xcresult`
- `xcodebuild-ui-test.log`
- pre-planning screenshot and UI tree
- planner request, response, validation, and failure summaries

Use `manifest.json` to discover files that actually exist instead of assuming every optional artifact was produced.

## Failure routing

- Scenario schema or path rejection: validate the checked-in/generated scenario first.
- Simulator or build failure: verify Xcode, shared scheme, destination, and build-for-testing output.
- Planner rejection: inspect the raw planner response and validation error; do not weaken the schema to accept invented IDs or launch values.
- Runner failure: inspect the app-owned summary, XCTest log, `.xcresult`, and failure screenshot.
- Element not found or wrong element type: invoke the companion `ios-ui-testability-contract` skill.
- Missing PR comment: verify workflow permissions, event type, author login, and token scope after confirming the artifact itself exists.

Canonical documentation: https://github.com/Kofiloski/ios-ai-ui-check
