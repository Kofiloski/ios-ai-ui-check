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
