# Adoption reference

## New app repository

Use a release-pinned checkout of the upstream repository. Replace the project and scheme values with the target app's real shared scheme.

```bash
git clone --branch v0.4.0 --depth 1 \
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
    uses: Kofiloski/ios-ai-ui-check/.github/workflows/run.yml@v0.4.0
    with:
      provided-scenario-path: .github/ai-ui/verify-primary-flow.json
```

This mode does not require a model API key.

## Planner mode

Use planner mode only when the app repository supplies and reviews its own planner command. The reusable action does not call a provider directly.

```yaml
- uses: Kofiloski/ios-ai-ui-check@v0.4.0
  with:
    planner-command: ./scripts/plan-ai-ui-scenario.sh
    planner-goal: Verify the most likely user-visible flow affected by this PR.
```

Give the planner only the context needed for the flow. A forked `pull_request` does not receive repository secrets.

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
