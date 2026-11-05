# ios-ai-ui-check

[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-View_Action-blue?logo=github)](https://github.com/marketplace/actions/ios-ai-ui-check)
[![CI](https://github.com/Kofiloski/ios-ai-ui-check/actions/workflows/ci.yml/badge.svg)](https://github.com/Kofiloski/ios-ai-ui-check/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Kofiloski/ios-ai-ui-check)](https://github.com/Kofiloski/ios-ai-ui-check/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Run app-owned XCUITest flows on iOS Simulator and give pull requests reviewable screenshots, video, logs, `.xcresult`, and one managed summary comment.

Use a checked-in scenario for deterministic CI, or an optional planner with explicit **provider, model, and effort**. Native Anthropic and OpenAI planners and configurable OpenAI-compatible endpoints are supported. The app repository owns launch state, fixtures, identifiers, and assertions.

## Quick start

From an app repository with a buildable `.xcodeproj`, shared scheme, and available Simulator:

```bash
git clone --branch v0.6.0 --depth 1 \
  https://github.com/Kofiloski/ios-ai-ui-check.git ../ios-ai-ui-check

python3 ../ios-ai-ui-check/scripts/scaffold-app-repo.py \
  --repo-root . --project App.xcodeproj --scheme App

./scripts/local-ai-ui-check.sh --use-example-scenario
```

Review the generated scenario and launch settings before running. The starter launches and captures the app; add meaningful interactions and assertions for regression coverage. [Setup and safe upgrades](docs/getting-started.md).

## Add a pull-request check

After scaffolding, this reusable workflow runs the checked-in scenario without a model API key:

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

The scaffold also generates a manual and label-triggered workflow. See the [copyable examples](examples/README.md) for other integrations.

## Use the agent skill

```bash
gh skill install Kofiloski/ios-ai-ui-check ios-ai-ui-check@v0.6.0 --agent codex --scope user
```

Ask the agent to verify a UI flow locally, reproduce a bug, or add a repeatable CI check. Local exploration uses available native Xcode Simulator tools; the supported baseline is Xcode/XCTest and Apple's command-line tools. Third-party inspectors are optional. [Native setup and evidence limits](docs/native-xcode-checks.md).

## Choose a planner

With `ANTHROPIC_API_KEY` set, an app with the v0.6.0 scaffold can run:

```bash
./scripts/local-ai-ui-check.sh \
  --provider anthropic --model claude-sonnet-4-6 --effort high \
  --goal "Verify settings persist after reopening the app"
```

The action inputs are `planner-provider`, `planner-model`, and `planner-effort`. Effort support varies by model. Existing integrations need an explicit scaffold refresh and updated action pin; these settings do not change the coding-agent session. [Provider configuration and credentials](docs/planner-configuration.md).

## Evidence and limits

Inspect the real summary, artifact manifest, media, and XCTest results together. A passing scenario proves its assertions; local touch actions or screenshots do not establish hosted CI coverage or backend correctness.

The public action delegates model calls to the app-owned planner. Review what source, UI state, and screenshots it sends before supplying credentials. Deterministic scenarios need no model key.

## Documentation

| Need | Guide |
| --- | --- |
| Scaffold or refresh an app | [Setup and upgrades](docs/getting-started.md) |
| Inputs, outputs, and scenario JSON | [Action reference](docs/action-reference.md) |
| PR, release-comparison, or existing-CI workflows | [Integration patterns](docs/integration-patterns.md) |
| Implement an app runner | [Runner contract](docs/runner-contract.md) |
| Find artifacts and interpret results | [Artifact manifest](docs/artifact-manifest.md) |
| Understand ownership and execution | [Architecture](docs/architecture.md) |
| Contribute or cut a release | [Development](docs/development.md) · [Releases](docs/releases.md) |

Companion tools: [UI Testability Contract](https://github.com/Kofiloski/ios-ui-testability-contract-skill) repairs app-side automation failures; [App Store Review Risk](https://github.com/Kofiloski/app-store-review-risk) checks likely submission risks.

MIT licensed. Agent discovery: [llms.txt](llms.txt). Citation metadata: [CITATION.cff](CITATION.cff).
