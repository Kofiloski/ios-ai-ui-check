# ios-ai-ui-check

[![CI](https://github.com/Kofiloski/ios-ai-ui-check/actions/workflows/ci.yml/badge.svg)](https://github.com/Kofiloski/ios-ai-ui-check/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Kofiloski/ios-ai-ui-check)](https://github.com/Kofiloski/ios-ai-ui-check/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Turn an app-owned `XCUITest` flow into a reviewable pull-request check: run it on iOS Simulator, preserve the evidence, and keep one managed PR summary up to date.

`ios-ai-ui-check` is a reusable GitHub Action plus a deterministic app-repo scaffold. It gives you:

- checked-in JSON scenarios for repeatable checks, or an optional planner command for goal-driven scenarios
- canonical scenario validation before the final scenario runner starts
- video, screenshots, logs, `.xcresult`, failure evidence, and a machine-readable artifact manifest
- a PR comment that links the artifact bundle and embeds the runner's real `summary.md`
- controlled failure artifacts when planning or execution fails, instead of a bare red check

The reusable action owns orchestration and evidence. Your app repo keeps control of launch state, data seeding, accessibility identifiers, UI interactions, and assertions.

## Start With A Deterministic Check

First scaffold the app-owned runner and scenario from a local checkout:

```bash
git clone --branch v0.3.0 --depth 1 \
  https://github.com/Kofiloski/ios-ai-ui-check.git ../ios-ai-ui-check

python3 ../ios-ai-ui-check/scripts/scaffold-app-repo.py \
  --repo-root . \
  --project App.xcodeproj \
  --scheme App

./scripts/local-ai-ui-check.sh --use-example-scenario
```

The scaffold writes a fuller manual and label-triggered workflow. If you prefer the smallest explicit deterministic caller, copy this after reviewing the generated scenario:

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
    uses: Kofiloski/ios-ai-ui-check/.github/workflows/run.yml@v0.3.0
    with:
      provided-scenario-path: .github/ai-ui/verify-primary-flow.json
```

This path does not call a model or require an API key. When GitHub restricts the default token on a fork or Dependabot pull request, the optional managed comment is skipped without failing the UI check; artifacts and the job summary still carry the evidence. A caller-provided writable `github-token` remains supported. Pin to a commit SHA instead of a release tag if your dependency policy requires immutable source references. A copyable version of the workflow lives in [`examples/deterministic-pr-check.yml`](examples/deterministic-pr-check.yml).

## Review Evidence, Not Just A Status Dot

The managed PR comment uses the actual action status, artifact URL, and app-runner summary. Its rendered shape is:

```md
## iOS AI UI Check

Status: `passed`

Artifact: [ios-ai-ui-check](https://github.com/.../actions/runs/.../artifacts/...)

## iOS AI UI Check

- Scenario: Verify primary flow
- Result: passed
- Simulator: iPhone 17 Pro / iOS 26.2 (...)
- Log: xcodebuild-ui-test.log
- Result bundle: AppUITests.xcresult
```

By default, the linked bundle can contain:

```text
summary.md
manifest.json
scenario.json
run.mp4                         # when recording finalizes successfully
failure-screenshot.png          # when XCTest provides a failure attachment
<UITestTarget>.xcresult/
xcodebuild-ui-test.log
inspect/                         # before-planning screenshot and UI tree
planner-*                        # request, response, validation, and summary evidence
```

`manifest.json` indexes the files that actually exist, so downstream tooling does not need to scrape Markdown or assume every optional artifact was produced. Planner failures still preserve a top-level summary and planner diagnostics before the action reports failure.

## How The Boundary Works

```mermaid
flowchart LR
  Provided["Checked-in scenario"] --> Validate["Canonical validation"]
  Goal["Planner goal"] --> Inspect["Live UI inspect"]
  Inspect --> Planner["App-owned planner command"]
  Planner --> Validate
  Validate --> Simulator["Boot Simulator + record video"]
  Simulator --> Runner["App-owned XCUITest runner"]
  Runner --> Evidence["Summary + manifest + media + logs + xcresult"]
  Evidence --> Review["Artifact upload + managed PR comment"]
```

The composite action does not call an AI provider. A checked-in scenario stays fully deterministic. On the optional AI path, the reusable workflow can expose a planner secret, but only the `planner-command` supplied by the app repo consumes it. That command chooses the provider and exactly what context leaves the runner. The generated planner is an OpenAI-backed example and can receive the inspected screenshot, UI tree, planner context, and discovered UI identifiers, so review it before adding credentials. Replace it with another provider or a local planner without changing the action contract.

## Companion Tools

- [`ios-ui-testability-contract-skill`](https://github.com/Kofiloski/ios-ui-testability-contract-skill) diagnoses and repairs app-side identifier, element-exposure, and deterministic-routing failures when a UI check cannot reach the intended control.
- [`app-store-review-risk`](https://github.com/Kofiloski/app-store-review-risk) scans Apple-platform repos for likely App Review, privacy, entitlement, StoreKit, metadata, and submission risks.

The action remains intentionally narrower than either companion: it runs and reports UI scenarios, while app testability and submission policy stay in their dedicated tools.

For agent and catalog ingestion, [`llms.txt`](llms.txt) provides a compact map of the contracts, examples, and verification commands.

## What The App Repo Must Own

- a buildable `.xcodeproj` with a shared scheme and a Simulator destination available on the selected macOS runner
- deterministic launch state through arguments, environment, deep links, fixtures, mocks, or a test account
- stable accessibility identifiers for controls and assertions in the intended flow
- an app-owned runner, normally the scaffolded `XCUITest` target and shell wrapper
- either a checked-in scenario or a planner command that emits the same provider-neutral scenario JSON

If you need the macOS runner to be configurable, use the reusable workflow wrapper in [`.github/workflows/run.yml`](.github/workflows/run.yml). A composite action step cannot choose `runs-on`.

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

If you use the scaffolded planner, also add `OPENAI_API_KEY` in the app repo.

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

For new repo setup, release pinning, safe refresh rollout, and the machine-readable artifact index, see [docs/adoption-checklist.md](docs/adoption-checklist.md), [docs/releases.md](docs/releases.md), and [docs/artifact-manifest.md](docs/artifact-manifest.md).

## Configure The Generated Integration

### 1. Review The Generated Planner Context

The scaffolded runner is generic. Review both the checked-in scenario example and `.github/ai-ui/planner-context.md`. The default AI planner becomes much more reliable once you describe the app's deterministic launch settings, preferred flow, and stable IDs there.

If the app has multiple startup states, fill in the exact launch flags or environment values that force the intended one. Without that guidance, the scaffolded planner now falls back to a safer launch-and-capture scenario instead of inventing placeholder test flags.
The scaffolded planner also treats source-discovered environment keys as weak hints only. It will not synthesize a value for a discovered key unless the exact key-value pair is documented in the planner context or checked-in scenario example.
The action also validates AI-generated step IDs against source-discovered `accessibilityIdentifier` literals when it can find them in the app repo. If the planner references an unknown ID, or a conditional ID such as an empty-state or paywall target that is not visible in the inspected UI and not documented in `.github/ai-ui`, the planning step fails fast instead of running a misleading UI test.
When AI planning is active, the action also captures a live before-planning screenshot and UI tree snapshot and passes them into the scaffolded planner.
That screenshot is written as `inspect/before-planning-screenshot.png`, and the matching UI tree is written as `inspect/before-planning-ui-tree.json`. Treat both as planning/debug context rather than final result artifacts.
When planning fails, the uploaded artifact still includes `summary.md`, `planner-summary.md`, `planner-request.md`, the raw planner response as `planner-response.json` or `planner-response.txt`, and `planner-validation-error.txt` when contract validation rejected the generated scenario. The generated planner now writes a raw draft scenario JSON before app-specific validation, so rejected scenarios remain inspectable in `planner-response.json` instead of disappearing into stderr. The artifact root also includes `manifest.json`, which enumerates the primary planner, inspect, media, and summary artifacts for downstream tooling.
Keep expectations realistic: XCUITest on Simulator is much slower than unit tests, and the hierarchy snapshot is debugging context for planning rather than a stable assertion source.

### 2. Use The Action After Your Existing Build/Test Steps

The examples below use the immutable `Kofiloski/ios-ai-ui-check@v0.3.0` release. Pin to a full commit SHA instead when your dependency policy requires it.
The scaffolded workflow supports both `workflow_dispatch` and opt-in `pull_request` runs. On PRs, it runs only when the `ai-ui-check` label is present and the scaffolded planner defaults to a PR-aware goal sentence.

The generated workflow keeps the manual GitHub form fairly narrow. It exposes `planner_goal` plus the technical knobs `simulator_name`, `simulator_runtime`, and `planner_model`. `planner_goal` maps to `AI_UI_PLANNER_GOAL`, so maintainers can ask for goals like `test adding an ingredient` without hand-authoring scenario JSON. When a planner goal is used, the action persists the exact goal text into `summary.md`, and the scaffolded planner can also emit a short `Planner Note` when it intentionally narrows a requested conditional-state path into a safer deterministic route. If the runner attached XCTest's `Failure Screenshot`, the action also extracts it from `.xcresult` into `failure-screenshot.png` before uploading artifacts. On pull requests, the action updates a single managed comment instead of posting a fresh new comment on every run, and it truncates oversized summaries instead of letting GitHub reject the whole update.
The lower-level action still supports further overrides such as checked-in scenarios and expected screenshots. The scaffolded workflow just does not surface those as `workflow_dispatch` form fields. If you need them, edit the workflow YAML directly or call the action from a custom workflow.
The generated workflow also supports a repository variable named `IOS_AI_UI_CHECK_REF`. Set that variable to a tag such as `v0.3.0`, a moving tag such as `v0`, or a commit SHA when you want the secondary checkout to pin to a specific reusable-repo version. If the variable is absent, the generated workflow falls back to `main`. This repo also ships a manual [release workflow](.github/workflows/release.yml) that runs the release-readiness suite, creates the requested semantic tag, optionally updates the moving major tag, and then creates the GitHub release notes.

#### AI-Planned Scenario

```yaml
- name: Build and test
  run: ./scripts/ci-test.sh

- name: UI validation
  if: success()
  uses: Kofiloski/ios-ai-ui-check@v0.3.0
  with:
    planner-command: ./scripts/plan-ai-ui-scenario.sh
    planner-goal: test adding an ingredient
    simulator-name: iPhone 17 Pro
    simulator-runtime: "26.2"
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

#### Provided Scenario Override

```yaml
- name: Build and test
  run: ./scripts/ci-test.sh

- name: UI validation
  if: success()
  uses: Kofiloski/ios-ai-ui-check@v0.3.0
  with:
    provided-scenario-path: .github/ai-ui/detail-screen.json
    simulator-name: iPhone 17 Pro
    simulator-runtime: "26.2"
```

## Inputs

Conditionally required:

- `planner-command`: required when no scenario file is available

Optional:

- `provided-scenario-path`: explicit checked-in scenario path; leave it empty to use AI planning, or point it at a checked-in scenario file for a deterministic override
- `planner-goal`: optional short sentence describing what the planner should verify; when omitted on pull_request events, the scaffolded planner defaults to verifying the most likely user-visible flow affected by the PR
- `simulator-name`: default `iPhone 17 Pro`
- `simulator-runtime`: default `26.2`
- `expected-screenshot-path`: optional reference screenshot path passed through to the planner and runner; the public action does not perform built-in image diffing
- `artifacts-dir`: default `artifacts/ios-ai-ui-check`
- `upload-artifacts`: default `true`
- `record-video`: default `true`
- `comment-on-pr`: default `true`; mainly useful when a pull_request caller wants to suppress the default PR comment
- `github-token`: optional token override for managed PR comments; defaults to the current workflow token
- `comment-author-login`: default `github-actions[bot]`; set it to the GitHub login associated with `github-token` when using a custom user or bot token so reruns update the same comment
- `max-duration-seconds`: default `300`; applied independently to each inspection, planner, and runner command rather than as one shared end-to-end budget

## Outputs

- `status`
- `scenario-path`
- `summary-path`
- `video-path`: populated only when video recording is enabled and a non-empty recording finalized successfully; capture failures are reported but do not replace the UI-check result
- `artifact-url`
- `before-planning-ui-tree-path`: populated when AI planning captured a pre-planning UI tree
- `before-planning-screenshot-path`: populated when AI planning captured a pre-planning screenshot
- `planner-note-path`: populated when AI planning emitted a short planner note sidecar
- `planner-request-path`: populated when AI planning was attempted and the action wrote a human-readable planner request summary
- `planner-response-path`: populated when AI planning was attempted and the action preserved the planner response, preferring `planner-response.json` over `planner-response.txt`
- `planner-validation-error-path`: populated when AI planning produced a scenario that failed schema or accessibility validation
- `planner-summary-path`: populated when AI planning was attempted and the action wrote a planner-side summary
- `resolved-source`: `provided` or `ai` when scenario resolution succeeded
- `failure-note`: high-level failure note when planning or runner execution failed
- `artifact-manifest-path`: path to `manifest.json`, the machine-readable artifact index

For compatibility with older callers, the action also still exposes deprecated aliases `current-ui-tree-path` and `current-screenshot-path` with the same values.

## Scenario Format

Example that matches the scaffolded `XCUITest` runner:

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

The action and the scaffolded planner now share one canonical scenario contract from `scripts/ai_ui_contract.py`, and [schemas/scenario.schema.json](schemas/scenario.schema.json) is the generated JSON copy of that same contract. The scaffolded runner understands `launch`, `tap`, `type`, `wait`, `assertVisible`, `assertText`, and `screenshot`. App-specific runners can support more, but the public action and generated planner only rely on the shared contract above.

## Maintaining This Repo

For repo maintenance, treat `scripts/ai_ui_contract.py` as the canonical source for:

- scenario validation rules
- source discovery for accessibility identifiers and launch hints
- the generated JSON schema in `schemas/scenario.schema.json`

The scaffold script copies that helper into app repos, and the generated planner imports it locally. If you change the contract or discovery heuristics, update the canonical helper first and then refresh the checked-in schema copy:

```bash
python3 scripts/ai_ui_contract.py write-schema --output schemas/scenario.schema.json
```

The repo now includes focused Python unit tests for the shared contract and scaffold metadata:

```bash
python3 -m unittest discover -s tests
```

For the most common maintenance loop, use:

```bash
./scripts/check-maintenance.sh
```

The same maintenance suite also runs automatically on every branch push and pull request through [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

Before cutting a release tag, use:

```bash
./scripts/check-release-readiness.sh
```

## Planner Command Contract

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

This repo does not hard-code an AI provider. The planner command can call OpenAI, another model provider, or a local planning tool. The scaffolded default planner uses OpenAI, but you can replace that generated planner script and use any provider you want.

## Planner Secrets

The default scaffolded planner uses `OPENAI_API_KEY`. The API key belongs in the app repo workflow, not in `ios-ai-ui-check`. Model selection is passed through the provider-neutral `AI_UI_PLANNER_MODEL` environment variable.

Pass it as an environment variable on the workflow step or job that uses the action. The planner command inherits that environment and can read the key directly.
If you use the reusable workflow wrapper instead of the core action directly, pass the secret through `planner-api-key` and optionally change the exported environment variable name with `planner-api-key-env-name`.

Example with OpenAI:

```yaml
- name: UI validation
  uses: Kofiloski/ios-ai-ui-check@v0.3.0
  with:
    planner-command: ./scripts/plan-ai-ui-scenario.sh
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

The scaffolded setup expects `OPENAI_API_KEY` by default. If you replace the generated planner script with your own provider integration, common key names are:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`

The action does not read those keys itself. Only the app repo's `planner-command` script uses them. `OPENAI_API_KEY` is the default for the scaffolded planner; feel free to replace that planner with your own and use a different key name.

## Runner Contract

The app repo runner contract lives in [docs/runner-contract.md](docs/runner-contract.md). The scaffolded path writes `./scripts/run-ai-ui-scenario.sh` and satisfies that contract for you.

## Integration Modes

This action supports multiple adoption patterns:

- manual smoke runs from the Actions tab through a `workflow_dispatch` workflow
- opt-in PR runs gated by a label such as `ai-ui-check`
- required PR checks integrated into an existing CI workflow
- a reusable workflow wrapper when you want the action to own the whole job

See [docs/integration-patterns.md](docs/integration-patterns.md) for concrete workflow examples and tradeoffs.

## Reusable Workflow Wrapper

This repo also includes [`.github/workflows/run.yml`](.github/workflows/run.yml).

Use it when you want to configure the macOS runner as an input. The wrapper defaults to `runs-on: macos-26` and:

- accepts the core action inputs, including simulator, artifact, video, and timeout controls
- checks out the caller repository
- checks out the action repository
- optionally exports a generic planner API key secret into the planner command environment through `planner-api-key` plus `planner-api-key-env-name`
- forwards the same outputs as the core action, including `artifact-manifest-path`
- invokes the same local action

Use the core action directly when you want to plug into an existing job. Use the reusable workflow when you want the action to own the job.

## Limitations

- This repo does not execute UI actions by itself. The repo-local runner must do that.
- The scaffolded runner is a baseline, not a full exploratory agent.
- The action assumes Xcode command-line tools are available on the runner.
- PR comments require a token with permission to write pull request comments.
- AI planning on forked PRs may need extra workflow policy because secrets are often unavailable.

## Repository Layout

```text
action.yml
.github/workflows/run.yml
CITATION.cff
llms.txt
examples/
scripts/
templates/
schemas/
docs/
```

- `action.yml`: composite-action contract plus GitHub Marketplace metadata
- `examples/`: copyable post-scaffold workflow callers
- `scripts/`: shell entry points used by the public action plus the deterministic scaffold generator
- `templates/`: `.tpl` source files rendered by the scaffold generator into an app repo; they are not executed directly
- `schemas/`: reference JSON schemas for scenario payloads
- `docs/`: durable architecture and runner contract notes
- `llms.txt` and `CITATION.cff`: agent-readable discovery and citation metadata

## Releases And Citation

Use immutable semantic tags such as `v0.3.0`, the moving compatibility tag `v0`, or a full commit SHA. See [docs/releases.md](docs/releases.md) for the release and scaffold-upgrade policy.

The project is MIT licensed. If you reference it in research, documentation, or a tool catalog, use [`CITATION.cff`](CITATION.cff) for the current citation metadata.
