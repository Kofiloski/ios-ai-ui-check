---
summary: Run diff-driven UI test generation for upstream releases and retain scoped historical evidence.
read_when:
  - Automating release comparisons or replaying older release pairs
  - Configuring the release-check reusable workflow or app release profile
  - Distinguishing generated release tests from fixed scenario baselines
---

# Release-diff UI regression checks

The release orchestrator is a new, unreleased workflow on `main`; pin its reviewed
commit, not `v0.6.0`. The existing action and provider adapters are reused. Its
generated tests are JSON scenarios executed by the native XCTest interpreter,
not new Swift source files compiled for each release.

The flow is: resolve stable iOS tags → pin previous/new commits → apply the
app-owned test harness to that exact head → collect the complete diff and release
notes → build and inspect → generate new tests tied to changed files → execute
each test → archive an immutable per-release attempt report.

## App-owned integration

The working integration shape lives in the independent [Proton Pass], [Firefox]
and [DuckDuckGo] forks. Their `skills-public-check.yml` workflows remain fixed
baseline checks. `skills-release-regression.yml` calls the new release pipeline.
The release pipeline never substitutes a baseline when planning is blocked.

[Proton Pass]: https://github.com/Kofiloski/ios-pass
[Firefox]: https://github.com/Kofiloski/firefox-ios
[DuckDuckGo]: https://github.com/Kofiloski/apple-browsers

`.github/ai-ui/release-profile.json` records the upstream repository, stable-tag
regex with numeric version capture groups, immutable harness seed, native
project/scheme/test target, build commands, runner and reviewed launch presets.
The optional maximum case count is 1–5 (default 3). The app owns these choices;
the reusable layer does not guess login state or replace app behavior.

An integration needs a generic `ScenarioRunnerUITests` in its native test target,
an inspect-capable wrapper and a focused test plan. The existing scaffold's
Swift interpreter and shell runner are reused. Fixed-selector adapters alone
cannot execute new generated scenarios. Do not discard stronger existing tests;
keep them as separately named baseline or unit-test checks.

Harness preparation excludes README/docs/workflow changes from the patch and
checks that the patch applies before building. It never falls back to the seed
commit if an older/newer release is incompatible. Such attempts are blocked and
retained. Historical replays require compatible Xcode, dependencies and harness
configuration, not just an available Git tag.

## Provider and scheduling

Set the selected provider's API key as a repository secret. The caller supports
explicit provider/model/effort inputs and `AI_UI_PLANNER_*` repository variables.
`AI_UI_PLANNER_API_KEY` is an explicit neutral override; otherwise only the
selected provider's named key is used. Anthropic is the example caller default.
The reusable workflow also accepts a compatible endpoint base URL. See
[planner configuration](planner-configuration.md).

Run manually first. Missing keys are detected before starting macOS builds, and
the result is a blocked report with a failing workflow, not UI success. Once a
live run has been reviewed, set `ENABLE_RELEASE_CHECKS=true` in the fork to enable
its daily poll. No model keys are configured in the example forks as of this
implementation; live model generation remains unverified.

First discovery queues only the latest matching pair. It snapshots older tags
without scheduling a costly whole-history backfill. Later unseen or moved tags
enter a persisted queue, including hotfix tags with a lower version than the
latest main release. Each published attempt advances that queue, including
blocked attempts, so one unsupported release cannot starve the rest. Explicit
`head_tag`/`base_tag` inputs replay older pairs; `force` retries the latest after
configuration is repaired. Failed/blocked releases are never relabelled passed.

Proton currently uses stable version tags without GitHub release entries.
DuckDuckGo's stable `+ios` tags exclude `-build+ios` TestFlight tags and macOS
tags. Firefox selects only `firefox-v*` tags. Tag-only releases retain actual
commit subjects with an explicit unavailable-release-notes label; these are not
invented changelogs. Profiles need maintenance if upstream tag formats change.

## Generation and coverage

The trusted planner job recomputes the immutable Git diff and verifies the
inspection artifact's identities, full diff hash and bounded excerpt before
calling the selected provider. It sends the diff, notes, reviewed launch
presets, discovered identifiers/labels, native hierarchy and screenshot.

The response contains `tests` and `uncovered`. Each test has a safe unique ID,
a changed-behavior claim, actual changed files, and a schema-valid scenario.
Every scenario begins with a reviewed launch preset and contains an assertion.
Unknown files, invented launch configuration, empty smoke tests, duplicate IDs
and unsupported runtime steps fail validation. No assertions are weakened to
obtain a green result. Files not explained by the model are automatically marked
unassessed. Zero generated executable tests cannot pass.

Cases execute independently through `ios-ai-ui-check`, with the new generated
scenario supplied to that action. Native result summaries must show exactly one
passed, unskipped XCTest per successful case. Runner exit code or a screenshot
alone cannot establish success. A report records passed/failed/not-executed
cases and uncovered changes. A model's association between a changed file and
an assertion is proposed coverage, not mechanical proof of semantic completeness.
Review those claims and the actual media/results before publishing broad claims.

## Job and artifact boundaries

Discovery and history run on Ubuntu. Native build/inspection and scenario
execution use separate macOS jobs without model credentials and read-only repo
permissions. The credentialed Ubuntu planner runs trusted orchestration only;
it never executes upstream app scripts. Relocatable test products move between
the native jobs in a tar archive preserving executable modes; extraction uses
Python's data filter. Only the history job receives repository write permission.
Do not combine these jobs just to avoid the product artifact transfer.

Each attempt stores JSON/Markdown reports and compressed source/test evidence
as release assets on the *fork*, under `ui-check-<comparison hash>`. Asset names
include run ID and attempt; existing attempts are not overwritten. The separate
`ui-check-state` release retains discovery snapshots. These are engineering
reports, not app releases. Compiled build products remain short-lived Actions
artifacts; reports retain source identities and native `.xcresult`/media/logs.
Evidence over GitHub's per-asset limit fails publication explicitly. Reports
remain independent of the ordinary Actions retention window. No upstream
issues, release tags, PR comments or notifications are created by this flow.

## Validation

Run `python3 -m unittest discover -s tests -p test_release_check.py` for discovery,
historical pairs, queue behavior, schema/launch/file validation, empty/skipped
native results, and real Git harness/comparison isolation. The existing adapter
tests cover provider transports. These checks do not prove a live model selected
useful tests or that a full app built at a new historical release. Report that
separately from static contracts, fixtures, generic Swift typechecking and the
older fixed-baseline passes.
