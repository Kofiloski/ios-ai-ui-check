---
summary: Overview of the public action, the reusable workflow wrapper, and the repo-local runner split.
read_when:
  - designing the public action interface
  - changing how planning, execution, artifacts, or PR comments work
---

# Architecture

The repo is intentionally split into two layers.

The public repo also owns a small shared Python contract helper used by both the composite action and the scaffolded planner template. That keeps scenario validation and source discovery from drifting across the two layers. The scaffold manifest now also records which generated files are reusable-layer managed versus app-customizable, plus the recorded content hashes for those generated files, so refreshes can preserve app-owned context by default and report drift before overwriting managed files. The public layer also writes an artifact `manifest.json` so uploaded bundles are machine-readable instead of relying only on markdown summaries.

## Public Layer

The public layer lives in this repo and owns:

- action inputs and outputs
- scenario resolution
- live UI inspection before AI planning
- simulator boot
- video capture
- artifact upload
- managed pull request commenting

This layer should stay generic and provider-agnostic.

## App Repo Layer

The app repo owns:

- data seeding
- login and test-state setup
- app launch details
- mapping scenario steps to actual UI automation
- UI assertions

This logic belongs in the repo-local runner because it depends on accessibility identifiers, deep links, launch arguments, and app-specific test hooks.

This repo also ships a deterministic scaffold generator that can create the baseline app-side files, including a UI test target, shared-scheme wiring, runner script, planner script, planner context, scenario override file, and optional workflow.

## Scenario Resolution

The action resolves one of two scenario sources:

- use an explicitly provided checked-in scenario file when configured
- otherwise inspect the current app state and run a planner command that writes scenario JSON

When the planner path is used, the public layer validates the generated scenario structure and, when source-discovered accessibility identifiers are available, rejects unknown IDs plus undocumented conditional IDs before simulator execution. The planner can also optionally emit a short note sidecar when it intentionally narrows a requested conditional-state path into a safer deterministic route, and the public layer appends that note to `summary.md`.
Planner failures are treated as controlled action failures rather than hard step aborts. The public layer preserves `planner-request.md`, the raw planner response as `planner-response.json` or `planner-response.txt`, `planner-validation-error.txt` when validation fails, `planner-summary.md`, and a top-level `summary.md` before the composite action fails at the end. The generated planner contract now also supports `AI_UI_PLANNER_DRAFT_SCENARIO_PATH`, which lets scaffolded app-side planners save raw scenario JSON before app-specific validation rejects it.

The core action does not call a specific model vendor directly. That concern is delegated to the planner command. The generated scaffold defaults that planner command to an OpenAI-backed script, but that is only a scaffold choice, not a public-action requirement.

## Why The Reusable Workflow Exists

An action step cannot choose the runner. `runs-on` is a job-level concern in GitHub Actions.

The reusable workflow exists to expose `runner` as an input while still using the same public action internally.
