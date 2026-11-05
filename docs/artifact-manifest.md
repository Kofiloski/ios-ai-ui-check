---
summary: Machine-readable contract for the `manifest.json` artifact index written by ios-ai-ui-check.
read_when:
  - consuming ios-ai-ui-check artifacts from another tool or workflow
  - changing uploaded artifact names or adding new primary artifact outputs
  - deciding whether markdown summaries are sufficient or structured artifact discovery is needed
---

# Artifact Manifest

`ios-ai-ui-check` writes `manifest.json` into the artifact root on every run, including planner failures that stop before the runner starts.

Use it when another workflow, local helper, or debugging tool needs stable artifact discovery without scraping `summary.md`.

## Top-Level Shape

Current fields:

- `schema_version`
- `tool`
- `generated_at_utc`
- `status`
- `resolved_source`
- `failure_note`
- `artifacts_dir`
- `primary_artifacts`
- `artifacts`

## Primary Artifacts

`primary_artifacts` is a map from stable logical keys to relative artifact paths when those artifacts exist.

Current logical keys include:

- `summary`
- `scenario`
- `video`
- `failure-screenshot`
- `before-planning-ui-tree`
- `before-planning-screenshot`
- `planner-note`
- `planner-request`
- `planner-response`
- `planner-validation-error`
- `planner-summary`

These keys are the safest contract for downstream consumers.

## Artifact Entries

Each item in `artifacts` includes:

- `key`
- `category`
- `description`
- `relative_path`
- `kind`
- `media_type`

Depending on the artifact kind, it may also include:

- `size_bytes` for files
- `entry_count` for directories

The list includes both primary artifacts and additional discovered files or directories under the artifact root.

## Stability Rules

- Prefer `primary_artifacts` when you need one canonical file such as the summary or planner response.
- Treat `artifacts` as the full discovered inventory for browsing or generic tooling.
- `schema_version` should change only for breaking manifest-shape changes.
- Adding new primary artifact keys is backward-compatible.

## Current Intentional Limits

- The manifest is an index, not a full JSON schema for every nested artifact type.
- It does not currently hash artifact contents.
- It records relative paths and metadata, not semantic assertions about the artifact contents.

## Human-readable review evidence

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
