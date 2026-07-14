---
summary: Suggested release and upgrade policy for ios-ai-ui-check so consuming repositories can pin intentionally instead of tracking main forever.
read_when:
  - preparing a reusable-repo release
  - documenting how app repos should pin or upgrade the action
  - deciding how to roll out template or contract changes safely
---

# Releases

`ios-ai-ui-check` should be consumed as a versioned dependency once a repo moves past initial setup.
This repo now includes `.github/workflows/release.yml` so the release process is not just a docs convention.

## Recommended Tag Strategy

Use semantic tags:

- immutable release tags such as `v0.2.0`
- a moving major tag such as `v0`

That gives consuming repos two stable upgrade modes:

- conservative pin: `v0.2.0`
- opt into compatible updates: `v0`

Use a commit SHA only for temporary hotfix pinning or debugging.

## Generated Workflow Pinning

The scaffolded workflow supports repository variable `IOS_AI_UI_CHECK_REF`.

Recommended rollout:

1. keep the default `main` pin only during first setup
2. cut a release tag after the scaffold and contract behavior are stable
3. set `IOS_AI_UI_CHECK_REF` in each consuming repo to `v0` or a full release tag
4. test upgrades by changing only that variable

This keeps generated workflow YAML stable while still making upgrades explicit.

## Upgrade Path For App Repos

1. update `IOS_AI_UI_CHECK_REF` to the new tag or SHA
2. run the workflow once or run local smoke coverage
3. if scaffold templates changed, run:

```bash
python3 scripts/refresh-scaffold.py --repo-root /path/to/app-repo --dry-run
```

4. inspect reported local drift for scaffold-managed files
5. rerun without `--dry-run` when the refresh looks safe
6. refresh customizable files only when you explicitly want to replace app-owned planner or scenario context

## Release Readiness

Before cutting a tag, run:

```bash
./scripts/check-release-readiness.sh
```

That script runs the maintenance suite, verifies expected executable bits, and prints the current working-tree changes under `.github/workflows/`, `docs/`, `schemas/`, `templates/`, and `README.md`.

## Manual Release Workflow

Use `.github/workflows/release.yml` from the default branch.
The workflow rejects dispatches from any other branch and serializes release jobs so two tag updates cannot race each other.

Inputs:

- `version_tag`: semantic tag such as `v0.3.0`
- `update_major_tag`: when true, also force-update the matching moving major tag such as `v0`

The workflow will:

1. validate the requested semantic tag
2. verify that the run is on the repository default branch
3. run `./scripts/check-release-readiness.sh`
4. create and push the exact release tag, or verify that an existing tag points to the same commit
5. create the GitHub release notes if they do not already exist
6. optionally move the matching major tag

The release is resumable. Rerunning the same version from the same commit continues past an existing exact tag or GitHub release, while an exact tag that points to a different commit remains a hard failure.
