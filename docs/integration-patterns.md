---
summary: Supported ways to wire ios-ai-ui-check into an app repo, including manual smoke runs, label-triggered runs, and required PR checks.
read_when:
  - choosing how to adopt ios-ai-ui-check in an app repo
  - wiring the action into pull_request workflows
  - deciding whether the check should be manual, opt-in, or required
---

# Integration Patterns

`ios-ai-ui-check` can be integrated in a few different ways depending on how much coverage and enforcement you want.

The examples below use `OWNER_OR_ORG/ios-ai-ui-check@main` for immediate setup. Replace `OWNER_OR_ORG` with the published repository owner. For a stable integration, pin to a tag or commit SHA before making it required.

## 1. Generated Manual + PR Workflow

Use this when you want one scaffolded workflow that supports both maintainer-triggered runs from the Actions tab and opt-in pull request runs.

This is the generated path from `scripts/scaffold-app-repo.py`. GitHub documents `workflow_dispatch` as the manual trigger for workflows, and notes that the workflow file must exist on the default branch before it can be run manually.

```yaml
name: AI UI Check

on:
  workflow_dispatch:
    inputs:
      simulator_name:
        description: Simulator name for unit tests and UI automation
        required: false
        default: iPhone 17 Pro
        type: string
      simulator_runtime:
        description: iOS Simulator runtime version for unit tests and UI automation
        required: false
        default: "26.2"
        type: string
      planner_model:
        description: Model used by the generated planner script. The scaffolded planner defaults to OpenAI, but app repos can replace it with any provider.
        required: false
        default: gpt-5-mini
        type: string
      planner_goal:
        description: Optional short sentence describing what flow the planner should verify.
        required: false
        default: ""
        type: string
  pull_request:
    types: [opened, synchronize, reopened, labeled]

jobs:
  ai-ui-check:
    if: |
      github.event_name == 'workflow_dispatch' ||
      (github.event_name == 'pull_request' && contains(github.event.pull_request.labels.*.name, 'ai-ui-check'))
```

The generated workflow defaults to AI planning through `./scripts/plan-ai-ui-scenario.sh`.
The generated workflow exposes `planner_goal` plus the technical overrides `simulator_name`, `simulator_runtime`, and `planner_model`.
Maintainers can use `planner_goal` for a sentence-level request such as `test adding an ingredient` or `verify the main ordering flow`.
On pull requests, the generated workflow is opt-in through the `ai-ui-check` label and defaults the planner goal to `Verify the most likely user-visible flow affected by this PR.`
Advanced overrides such as a checked-in scenario path and expected screenshot path still exist at the action level. The scaffolded workflow keeps those out of the manual GitHub form on purpose. If you need that level of control, edit the workflow YAML directly or build a dedicated wrapper workflow.

When AI planning is active, the action first captures a before-planning UI tree snapshot and screenshot from the app repo's scaffolded runner, then passes that runtime context into the planner. The screenshot is uploaded under `inspect/before-planning-screenshot.png`, and the matching UI tree is uploaded under `inspect/before-planning-ui-tree.json`. These are pre-planning artifacts, not final scenario result artifacts.

It starts simulator boot and `build-for-testing` in the same step. The workflow waits only long enough to resolve the simulator UDID, kicks off the build against that UDID, and then waits for boot completion before the UI action. That gives you actual overlap instead of two serialized waits.

The generated workflow also writes a short timing summary to the GitHub step summary so you can see boot-to-ready and build-for-testing durations directly. The prewarm/build step tees `xcodebuild` output into `artifacts/ios-ai-ui-check/xcodebuild-build-for-testing.log`, so slow runs keep the raw build log in the final artifact bundle.

Keep expectations realistic: the XCUITest phase is still UI automation running against Simulator, so it will remain materially slower than unit tests even when the action avoids unnecessary extra work.

The scaffolded workflow checks out the action repository slug detected during scaffold generation. It uses repository variable `IOS_AI_UI_CHECK_REF` when it is set, and falls back to `main` otherwise.
Use that variable to move consuming repos from first-time setup on `main` to an explicit tag or SHA without editing the generated workflow file.

This generated workflow is intentionally a smoke workflow:

- it runs `build-for-testing`
- it reuses that build for the AI UI action
- it does not run the app repo's unit-test targets

Best use:

- first-time setup
- maintainer-driven smoke runs
- validating a new scenario before making it part of CI

If your published `ios-ai-ui-check` repo is private, add an `ACTION_REPO_TOKEN` repository secret in the app repo. The generated workflow uses that secret for the secondary checkout and falls back to `github.token` when the action repo is public.

If you use the scaffolded planner, also add `OPENAI_API_KEY` in the app repo.
For pull requests from forks, GitHub does not expose repository secrets to `pull_request` workflows. AI-planned PR runs therefore require a maintainer-owned branch, another credential strategy, or a deterministic checked-in scenario instead.

If the app has multiple startup states, fill in `.github/ai-ui/planner-context.md` with the exact launch flags or environment values that force the intended one. The scaffolded planner is intentionally conservative when that guidance is missing.
Treat the generated planner context and checked-in scenario as starter files, not authoritative truth. The reusable scaffold can create the integration shape, but each app repo still needs to own its deterministic launch rules, stable identifiers, and app-specific flow guidance.
The uploaded artifact bundle also includes `manifest.json`, which is useful if another workflow or local inspection tool wants to reason about artifact paths without scraping `summary.md`.

## 2. Label-Triggered PR Run

Use this when you want the check to be opt-in for pull requests instead of always running and you prefer a dedicated PR workflow instead of the generated hybrid workflow.

Recommended pattern:

- trigger on `pull_request`
- include `labeled` in `types`
- gate the job on a label such as `ai-ui-check`
- also include `synchronize` so the job reruns on new commits while the label remains present

```yaml
name: AI UI Check

on:
  pull_request:
    types: [opened, synchronize, reopened, labeled]

permissions:
  contents: read
  pull-requests: write

jobs:
  ai-ui-check:
    if: contains(github.event.pull_request.labels.*.name, 'ai-ui-check')
    runs-on: macos-26
    steps:
      - uses: actions/checkout@v5

      - name: Build for testing
        run: |
          SIMULATOR_ARCH="$(uname -m)"
          xcodebuild build-for-testing \
            -project "App.xcodeproj" \
            -scheme "App" \
            -destination "platform=iOS Simulator,name=iPhone 17 Pro,OS=26.2,arch=$SIMULATOR_ARCH" \
            -parallel-testing-enabled NO \
            -derivedDataPath .derivedData/ci

      - name: Run AI UI action
        uses: OWNER_OR_ORG/ios-ai-ui-check@main
        with:
          planner-command: ./scripts/plan-ai-ui-scenario.sh
          planner-goal: Verify the most likely user-visible flow affected by this PR.
          simulator-name: iPhone 17 Pro
          simulator-runtime: "26.2"
        env:
          AI_UI_DERIVED_DATA_PATH: ${{ github.workspace }}/.derivedData/ci
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

Best use:

- expensive UI checks that you do not want on every PR
- maintainers requesting an extra UI pass before merge
- incremental rollout before the check becomes required

If your app repo uses the scaffolded planner, a good default PR goal is:

- `Verify the most likely user-visible flow affected by this PR.`

Security note:

- GitHub documents `pull_request_target` as running in the base repository context and warns to avoid it when you need to build or run code from the pull request.
- For this action, prefer `pull_request` when you are compiling and running the PR's app code.

## 3. Existing PR CI Step

Use this when you already have a build-and-test workflow and want `ios-ai-ui-check` to become a normal PR check.

```yaml
name: CI

on:
  pull_request:
    branches: [main]

permissions:
  contents: read
  pull-requests: write

jobs:
  ci:
    runs-on: macos-26
    steps:
      - uses: actions/checkout@v5

      - name: Build for testing
        run: |
          SIMULATOR_ARCH="$(uname -m)"
          xcodebuild build-for-testing \
            -project "App.xcodeproj" \
            -scheme "App" \
            -destination "platform=iOS Simulator,name=iPhone 17 Pro,OS=26.2,arch=$SIMULATOR_ARCH" \
            -parallel-testing-enabled NO \
            -derivedDataPath .derivedData/ci

      - name: Run unit tests
        run: |
          SIMULATOR_ARCH="$(uname -m)"
          xcodebuild test-without-building \
            -project "App.xcodeproj" \
            -scheme "App" \
            -destination "platform=iOS Simulator,name=iPhone 17 Pro,OS=26.2,arch=$SIMULATOR_ARCH" \
            -parallel-testing-enabled NO \
            -derivedDataPath .derivedData/ci \
            -only-testing:AppTests

      - name: Run AI UI action
        uses: OWNER_OR_ORG/ios-ai-ui-check@main
        with:
          planner-command: ./scripts/plan-ai-ui-scenario.sh
          planner-goal: Verify the most likely user-visible flow affected by this PR.
          simulator-name: iPhone 17 Pro
          simulator-runtime: "26.2"
        env:
          AI_UI_DERIVED_DATA_PATH: ${{ github.workspace }}/.derivedData/ci
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

Best use:

- standard PR validation
- branch protection with a required status check
- sharing the same DerivedData and simulator setup as the rest of CI

Unlike the generated workflow, this path is where it makes sense to keep your unit-test step if your existing CI already runs it.

Practical note:

- GitHub recommends unique job names when you require status checks through branch protection. Keep the job name stable, for example `ai-ui-check`.

## 4. Reusable Workflow Wrapper

Use [`.github/workflows/run.yml`](../.github/workflows/run.yml) when you want the public repo to own the job and you want `runs-on` to be configurable as an input.

This is useful when:

- the app repo wants a thin calling workflow
- multiple repos should share the same top-level job shape
- you want to keep the app repo configuration small

The reusable workflow now forwards the same outputs as the core action, including `artifact-manifest-path`.
It also exposes the operational inputs that the core action already supports, such as artifact directory, artifact upload toggle, video toggle, and timeout.
For AI-planned flows, it provides a provider-agnostic secret pass-through using `planner-api-key` plus `planner-api-key-env-name`, so callers do not need to hard-code `OPENAI_API_KEY` into the reusable workflow itself.

## Choosing Between Them

- Use manual smoke runs first when bootstrapping a new app repo.
- Use the label-triggered mode when the check is expensive or still maturing.
- Use the existing PR CI step when the flow is stable and should gate merges.
- Use the reusable workflow wrapper when you want the job orchestration to live in the action repo instead of the app repo.
