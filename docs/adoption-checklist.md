---
summary: Short checklist for adopting ios-ai-ui-check in a new iOS repository without overfitting the reusable action to one app.
read_when:
  - scaffolding a new app repo
  - moving from a local smoke run to a PR workflow
  - validating whether an app repo is ready for AI UI checks
---

# Adoption Checklist

Use this as the minimum handoff checklist after running `scripts/scaffold-app-repo.py`.

## 1. Scaffold The Repo

- run the scaffold once against the real shared scheme
- commit the generated files before custom edits so future refreshes have a clean baseline
- confirm `.github/ai-ui/scaffold-manifest.json` exists

## 2. Review App-Owned Files

Do not treat these as reusable-repo truth:

- `.github/ai-ui/planner-context.md`
- the checked-in scenario JSON
- `scripts/plan-ai-ui-scenario.sh`

Review and tighten them for the actual app:

- exact launch arguments
- exact launch environment key-value pairs
- deterministic route or seeded state
- stable accessibility identifiers for the intended flow

## 3. Pin The Action Ref

Generated workflows support a repository variable named `IOS_AI_UI_CHECK_REF`.

Set it to one of:

- a release tag such as `v0.3.0`
- a moving major tag such as `v0`
- a commit SHA when you want a one-off hotfix pin

If the variable is absent, the generated workflow falls back to `main`.

## 4. Add Secrets Only When Needed

- add `OPENAI_API_KEY` if the scaffolded planner is enabled
- add `ACTION_REPO_TOKEN` only when the action repository is private

If PRs come from forks, remember that `pull_request` workflows do not receive repository secrets.

## 5. Verify The Contract Locally

- run `./scripts/local-ai-ui-check.sh --use-example-scenario`
- run `./scripts/local-ai-ui-check.sh --goal "<one concrete flow>"`
- inspect the before-planning screenshot and UI tree when the planner path is enabled

## 6. Choose The Right CI Mode

- use the generated hybrid workflow for initial smoke coverage
- use the label-triggered pattern when runs are still expensive or maturing
- move to a standard required PR check only after launch state and identifiers are stable

## 7. Refresh Safely

When the reusable repo changes, start with:

```bash
python3 scripts/refresh-scaffold.py --repo-root /path/to/app-repo --dry-run
python3 scripts/refresh-scaffold.py --repo-root /path/to/app-repo --check
```

The refresh wrapper reports local drift against the recorded scaffold hashes before replaying the scaffold command.
Use `--check --json` when another tool or CI job needs the drift report as structured data.

Managed files are safe to refresh aggressively.
Customizable files remain app-owned and are preserved unless you pass `--refresh-customizable-files`.
