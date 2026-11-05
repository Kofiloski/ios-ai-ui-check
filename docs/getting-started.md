---
summary: Scaffold, customize, run, and refresh the app-owned iOS UI integration.
read_when:
  - Adding ios-ai-ui-check to an app repository
  - Reviewing generated files, launch state, or scaffold refresh behavior
---

# App setup and upgrades

Start with the [README quick start](../README.md#quick-start). The commands below run from the action checkout unless a block explicitly changes into the app repository.

## What The App Repo Must Own

- a buildable `.xcodeproj` with a shared scheme and a Simulator destination available on the selected macOS runner
- deterministic launch state through arguments, environment, deep links, fixtures, mocks, or a test account
- stable accessibility identifiers for controls and assertions in the intended flow
- an app-owned runner, normally the scaffolded `XCUITest` target and shell wrapper
- either a checked-in scenario or a planner command that emits the same provider-neutral scenario JSON

If you need the macOS runner to be configurable, use the reusable workflow wrapper in [`.github/workflows/run.yml`](../.github/workflows/run.yml). A composite action step cannot choose `runs-on`.

## Bootstrap An App Repo

Use the scaffold script to generate the baseline files in an app repo:

```bash
python3 scripts/scaffold-app-repo.py \
  --repo-root /path/to/app-repo \
  --project App.xcodeproj \
  --scheme App \
  --simulator-name "iPhone 17 Pro" \
  --simulator-runtime "26.2"
```

Preview the scaffold without writing files:

```bash
python3 scripts/scaffold-app-repo.py \
  --repo-root /path/to/app-repo \
  --project App.xcodeproj \
  --scheme App \
  --dry-run
```

If you want the scaffold to reproduce an existing app-specific starter more closely, you can also pass:

- `--scenario-file-name add-recipe-form.json`
- `--scenario-template /path/to/app/.github/ai-ui/add-recipe-form.json`
- `--planner-context-template /path/to/app/.github/ai-ui/planner-context.md`

The scaffold script will:

- create or update a UI test target
- patch the shared Xcode scheme so the UI test target builds with the app
- write `Tests/<AppUITests>/ScenarioRunnerUITests.swift`
- write `scripts/run-ai-ui-scenario.sh`
- write `scripts/local-ai-ui-check.sh`
- write `scripts/plan-ai-ui-scenario.sh`
- write `scripts/ai_ui_contract.py`
- write `scripts/ai_ui_planner.py`
- write `.github/ai-ui/verify-primary-flow.json` or the file name you pass
- write `.github/ai-ui/planner-context.md`
- write `.github/ai-ui/scaffold-manifest.json`
- optionally write `.github/workflows/ai-ui-check.yml`

This setup step is fully deterministic. The scaffold script does not use an AI agent.
By default, the scaffolded scenario and planner context are generic starter files. App-specific guidance only appears if you edit those files after generation or supply them explicitly through `--scenario-template` and `--planner-context-template`.
Template improvements in `ios-ai-ui-check` apply to future scaffolds and explicit refreshes only. Existing app repos keep their generated files until you rerun the scaffold or patch those files manually.
Generated files now include lightweight provenance headers where the file format allows them, and the scaffold writes `.github/ai-ui/scaffold-manifest.json` with the originating action commit plus a portable refresh command. The recorded command contains no absolute app, action-checkout, or source-template paths. Run it from the app repo root after setting `IOS_AI_UI_CHECK_ROOT` to the current `ios-ai-ui-check` checkout you want to use; this keeps it valid when either checkout is moved or cloned elsewhere.
For a manifest-driven refresh, this repo also ships `scripts/refresh-scaffold.py`, which reads `.github/ai-ui/scaffold-manifest.json`, compares current generated files against recorded scaffold hashes, and then replays the scaffold with the recorded config.
External files passed through `--scenario-template` or `--planner-context-template` are initial seeds, not permanent machine-local dependencies. The manifest records the generated app-owned scenario or planner-context file as the portable source for later customizable refreshes. Templates already checked into the app repo remain repo-relative references.

```bash
cd /path/to/app-repo
export IOS_AI_UI_CHECK_ROOT=/path/to/ios-ai-ui-check
python3 "${IOS_AI_UI_CHECK_ROOT}/scripts/refresh-scaffold.py" --repo-root .
```

If `ios-ai-ui-check` is private, add an `ACTION_REPO_TOKEN` secret in the app repo so the generated workflow can check out the private action repository.

If you use the scaffolded planner, add `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or the generic `AI_UI_PLANNER_API_KEY` for the selected provider. See [planner configuration](planner-configuration.md) for source-version availability and setup.

The generated workflow is a smoke workflow. It builds the app for testing and runs the AI UI action, but it does not run the app repo's unit-test targets for you. It also writes a short timing summary to the GitHub step summary so boot and build durations are visible without reading interleaved logs by eye, and it writes `xcodebuild-build-for-testing.log` into the uploaded artifact directory for slow-build diagnosis.

Current scaffold limits:

- it targets standard `.xcodeproj` repos
- it expects a shared scheme to already exist
- it generates a baseline `XCUITest` runner, but you still need to review the launch environment and scenario so they match the app

### What The Scaffold Does Vs What You Still Customize

The scaffold can generate the integration shape for most iOS repos:

- a UI-test-based runner target
- the repo-local runner and planner scripts
- a starter workflow
- a checked-in scenario example
- a starter `.github/ai-ui/planner-context.md`

That output is intentionally generic. You should still treat these files as app-owned and review them before relying on AI-planned runs:

- `.github/ai-ui/planner-context.md`
- the checked-in scenario example
- `scripts/plan-ai-ui-scenario.sh`
- any accessibility identifiers needed by the intended flow

The scaffold does not automatically know:

- which launch arguments or environment values are actually deterministic for your app
- which flows are safe in CI versus network-dependent or flaky
- which accessibility identifiers represent the best stable assertions
- whether a requested goal should be narrowed to a safer local flow instead of asserting backend completion

In practice, the reusable repo owns the orchestration contract, while the app repo still owns the truth about launch state, identifiers, and what counts as a reliable flow.

Managed-file policy:

- scaffold-managed files are safe to refresh from the reusable repo
- customizable files are preserved by default during manifest-driven refreshes
- customizable files are currently `.github/ai-ui/planner-context.md` and the checked-in scenario JSON
- pass `--refresh-customizable-files` to `scripts/refresh-scaffold.py` when you intentionally want to overwrite those app-owned files too
- refresh dry-runs now report which generated files drifted from the recorded scaffold content before anything is overwritten

The scaffold also writes a human-oriented local helper script. Typical usage:

```bash
./scripts/local-ai-ui-check.sh --goal "test adding an ingredient"
./scripts/local-ai-ui-check.sh --use-example-scenario
./scripts/local-ai-ui-check.sh --scenario .github/ai-ui/verify-primary-flow.json
```

That helper now makes the mode explicit. It does not silently fall back from AI planning to the checked-in scenario example. If you want the example scenario, pass `--use-example-scenario`.

To refresh an existing scaffold from its manifest:

```bash
python3 scripts/refresh-scaffold.py --repo-root /path/to/app-repo
python3 scripts/refresh-scaffold.py --repo-root /path/to/app-repo --dry-run
python3 scripts/refresh-scaffold.py --repo-root /path/to/app-repo --refresh-customizable-files
python3 scripts/refresh-scaffold.py --repo-root /path/to/app-repo --check
python3 scripts/refresh-scaffold.py --repo-root /path/to/app-repo --check --json
```

For adoption checks, release pinning, safe refresh rollout, and the machine-readable artifact index, see [docs/adoption-checklist.md](adoption-checklist.md), [docs/releases.md](releases.md), and [docs/artifact-manifest.md](artifact-manifest.md).

## Configure The Generated Integration

### 1. Review The Generated Planner Context

The scaffolded runner is generic. Review both the checked-in scenario example and `.github/ai-ui/planner-context.md`. The default AI planner becomes much more reliable once you describe the app's deterministic launch settings, preferred flow, and stable IDs there.

If the app has multiple startup states, fill in the exact launch flags or environment values that force the intended one. Without that guidance, the scaffolded planner uses a safer launch-and-capture scenario instead of inventing placeholder test flags. Explicit release comparisons still require a visibility/text assertion; see [release comparisons](integration-patterns.md#release-comparisons).
The scaffolded planner also treats source-discovered environment keys as weak hints only. It will not synthesize a value for a discovered key unless the exact key-value pair is documented in the planner context or checked-in scenario example.
The action also validates AI-generated step IDs against source-discovered `accessibilityIdentifier` literals when it can find them in the app repo. If the planner references an unknown ID, or a conditional ID such as an empty-state or paywall target that is not visible in the inspected UI and not documented in `.github/ai-ui`, the planning step fails fast instead of running a misleading UI test.
When AI planning is active, the action also captures a live before-planning screenshot and UI tree snapshot and passes them into the scaffolded planner.
That screenshot is written as `inspect/before-planning-screenshot.png`, and the matching UI tree is written as `inspect/before-planning-ui-tree.json`. Treat both as planning/debug context rather than final result artifacts.
When planning fails, the uploaded artifact still includes `summary.md`, `planner-summary.md`, `planner-request.md`, the raw planner response as `planner-response.json` or `planner-response.txt`, and `planner-validation-error.txt` when contract validation rejected the generated scenario. The generated planner now writes a raw draft scenario JSON before app-specific validation, so rejected scenarios remain inspectable in `planner-response.json` instead of disappearing into stderr. The artifact root also includes `manifest.json`, which enumerates the primary planner, inspect, media, and summary artifacts for downstream tooling.
Keep expectations realistic: XCUITest on Simulator is much slower than unit tests, and the hierarchy snapshot is debugging context for planning rather than a stable assertion source.

### 2. Use The Action After Your Existing Build/Test Steps

The examples below use the immutable `Kofiloski/ios-ai-ui-check@v0.6.0` release. Pin to a full commit SHA instead when your dependency policy requires it.
The scaffolded workflow supports both `workflow_dispatch` and opt-in `pull_request` runs. On PRs, it runs only when the `ai-ui-check` label is present and the scaffolded planner defaults to a PR-aware goal sentence.

The generated workflow keeps the manual GitHub form fairly narrow. It exposes `planner_goal` plus the technical knobs `simulator_name`, `simulator_runtime`, `planner_provider`, `planner_model`, `planner_effort`, and `planner_base_url`. `planner_goal` maps to `AI_UI_PLANNER_GOAL`, so maintainers can ask for goals like `test adding an ingredient` without hand-authoring scenario JSON. When a planner goal is used, the action persists the exact goal text into `summary.md`, and the scaffolded planner can also emit a short `Planner Note` when it intentionally narrows a requested conditional-state path into a safer deterministic route. If the runner attached XCTest's `Failure Screenshot`, the action also extracts it from `.xcresult` into `failure-screenshot.png` before uploading artifacts. On pull requests, the action updates a single managed comment instead of posting a fresh new comment on every run, and it truncates oversized summaries instead of letting GitHub reject the whole update.
The lower-level action still supports further overrides such as checked-in scenarios and expected screenshots. The scaffolded workflow just does not surface those as `workflow_dispatch` form fields. If you need them, edit the workflow YAML directly or call the action from a custom workflow.
The generated workflow also supports a repository variable named `IOS_AI_UI_CHECK_REF`. Set that variable to a tag such as `v0.6.0`, a moving tag such as `v0`, or a commit SHA when you want the secondary checkout to pin to a specific reusable-repo version. If the variable is absent, the generated workflow falls back to `main`. This repo also ships a manual [release workflow](../.github/workflows/release.yml) that runs the release-readiness suite, creates the requested semantic tag, optionally updates the moving major tag, and then creates the GitHub release notes.

#### AI-Planned Scenario

```yaml
- name: Build and test
  run: ./scripts/ci-test.sh

- name: UI validation
  if: success()
  uses: Kofiloski/ios-ai-ui-check@v0.6.0
  with:
    planner-command: ./scripts/plan-ai-ui-scenario.sh
    planner-provider: anthropic
    planner-model: claude-sonnet-4-6
    planner-effort: high
    planner-goal: test adding an ingredient
    simulator-name: iPhone 17 Pro
    simulator-runtime: "26.2"
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

#### Provided Scenario Override

```yaml
- name: Build and test
  run: ./scripts/ci-test.sh

- name: UI validation
  if: success()
  uses: Kofiloski/ios-ai-ui-check@v0.6.0
  with:
    provided-scenario-path: .github/ai-ui/detail-screen.json
    simulator-name: iPhone 17 Pro
    simulator-runtime: "26.2"
```

## Limitations

- This repo does not execute UI actions by itself. The repo-local runner must do that.
- The scaffolded runner is a baseline, not a full exploratory agent.
- The action assumes Xcode command-line tools are available on the runner.
- PR comments require a token with permission to write pull request comments.
- AI planning on forked PRs may need extra workflow policy because secrets are often unavailable.
