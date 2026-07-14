---
summary: Maintenance notes for the shared scenario contract, scaffold provenance, and focused test surface in ios-ai-ui-check.
read_when:
  - changing scenario validation or planner discovery behavior
  - updating scaffolded templates or refresh behavior
  - verifying repo-level maintenance changes before release
---

# Development

## Canonical Contract

Treat `scripts/ai_ui_contract.py` as the canonical source for:

- scenario validation
- source discovery for accessibility identifiers and launch hints
- state-dependent identifier checks
- the generated JSON schema in `schemas/scenario.schema.json`

The public action imports that helper for scenario validation, and the scaffold copies the same helper into app repos so generated planners use the same contract logic.
The public action also writes a machine-readable `manifest.json` into each artifact bundle so downstream tooling can consume artifact paths without scraping markdown summaries.

## Schema Sync

When the contract changes, refresh the checked-in schema copy:

```bash
python3 scripts/ai_ui_contract.py write-schema --output schemas/scenario.schema.json
```

Do not hand-edit the schema copy unless you are also changing the canonical helper in the same diff.
The maintenance check regenerates the schema into a temporary file and fails on drift; it never repairs a stale checked-in schema during CI.

## Scaffold Provenance

The scaffold now writes `.github/ai-ui/scaffold-manifest.json` into generated app repos.

Use it to answer:

- which `ios-ai-ui-check` commit generated the scaffold
- which files were generated
- which refresh command should be rerun to pull in template changes
- which generated files are scaffold-managed versus app-customizable
- which recorded generated-file hashes still match the local repo

Generated shell, Swift, Markdown, and workflow files also carry a short header that points back to the manifest.
The manifest's `refresh_command` is location-independent: it expects to run from the app repo root and resolves the selected action checkout through `IOS_AI_UI_CHECK_ROOT`. It deliberately avoids recording absolute app, action-checkout, or template paths, so cloning or moving either repository does not stale the command.
An external scenario or planner-context template is treated as an initial seed. Its generated customizable file becomes the manifest's portable refresh source, while an original template that lives inside the app repo is recorded as a repo-relative source. The corresponding `*_template_mode` field makes that distinction explicit without retaining a machine-local path.

```bash
cd /path/to/app-repo
export IOS_AI_UI_CHECK_ROOT=/path/to/ios-ai-ui-check
python3 "${IOS_AI_UI_CHECK_ROOT}/scripts/refresh-scaffold.py" --repo-root .
```

## Managed File Policy

Treat scaffold output in two buckets:

- managed files: files the reusable repo owns and can refresh safely
- customizable files: files the app repo is expected to tailor to its own launch rules and UI contract

The manifest records both sets. The refresh wrapper preserves existing customizable files by default and refreshes managed files only.
When the manifest includes content hashes, the refresh wrapper also reports local drift before it replays the scaffold.

Use the refresh wrapper for manifest-driven refreshes:

```bash
python3 scripts/refresh-scaffold.py --repo-root /path/to/app-repo
python3 scripts/refresh-scaffold.py --repo-root /path/to/app-repo --dry-run
python3 scripts/refresh-scaffold.py --repo-root /path/to/app-repo --refresh-customizable-files
python3 scripts/refresh-scaffold.py --repo-root /path/to/app-repo --check
python3 scripts/refresh-scaffold.py --repo-root /path/to/app-repo --check --json
```

## Repo Tests

Run the focused maintenance suite with:

```bash
python3 -m unittest discover -s tests
```

For the common maintenance path, use:

```bash
./scripts/check-maintenance.sh
```

That same script now runs automatically on every branch push and pull request through `.github/workflows/ci.yml`.

Before cutting a reusable-repo release, use:

```bash
./scripts/check-release-readiness.sh
```

## Public Discovery Surfaces

Keep the public entry points consistent with the executable contract:

- `README.md` is the human adoption path and should show real generated artifacts rather than mock product screenshots.
- `action.yml` owns GitHub Marketplace metadata and branding; changing descriptions must not rename inputs or outputs.
- `llms.txt` is the compact agent-readable map to the architecture, runner contract, examples, and maintenance commands.
- `CITATION.cff` records the latest published release metadata.
- `examples/` contains copyable post-scaffold workflows and must use a real release or commit pin.

When a release supersedes the documented version, update the README, examples, `llms.txt`, and `CITATION.cff` together. Keep the deterministic example first so adoption does not imply that a model credential is required.

The repo now also ships `.github/workflows/release.yml` for manual release publication. That workflow runs the same readiness check, creates the requested semantic tag, optionally force-updates the moving major tag such as `v0`, and then creates the GitHub release notes.

Current coverage is aimed at the highest-drift surfaces:

- shared scenario contract and repo scanning
- schema sync against the canonical helper
- scaffold manifest and refresh command generation
- fixture-app scaffold and refresh smoke coverage
- planner failure summaries and PR comment rendering
- artifact manifest generation
- reusable-workflow contract forwarding
