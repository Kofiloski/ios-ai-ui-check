---
summary: Use explicit immutable comparison context and app-owned regression assertions for release checks.
read_when:
  - Changing release-comparison inputs or planner context
  - Interpreting a passing scenario as release coverage
---

# Explicit release comparisons

Date: 2026-11-04. Status: Accepted.

## Context and constraints

The Ice Cubes evaluation compared release 2.1.5 to 2.1.6 while its original UI checkout contained a later 2.1.7 revision. The unchanged planner's parent-commit fallback returned no diff in that shallow checkout. Its unreported 20,000-character excerpt also omitted part of the 38,109-byte release diff. A successful local settings test did not establish release coverage. The reusable layer must remain provider-agnostic and app behavior must remain app-owned.

## Decision

Accept explicit base/head refs and a local release-notes file. Resolve refs to commits and require the checkout to match the explicit head. Fail incomplete explicit/PR comparisons without falling back to an unrelated commit. Preserve the complete diff and machine-readable context while disclosing the bounded planner excerpt. Do not fetch history or infer the latest release automatically. Preserve existing goal-only workflows with an explicit unavailable-context warning.

Require an assertion in explicit release scenarios and state that a successful scenario covers only its executed behavior. Let app-owned XCTest implementations supply stronger assertions through the existing runner wrapper's test-selector override; keep inspection unchanged. Release claims beyond the executed scenario need an app-owned coverage report.

## Alternatives considered

- Automatically selecting/fetching the latest release obscures provenance and adds network permissions to planning; callers can resolve and pin tags deliberately.
- Falling back from an unavailable PR/release diff to `HEAD^` can silently test an unrelated change, so explicit comparisons fail instead.
- Expanding the JSON action set with app-specific network/state assertions would couple the reusable runner to consumers; focused app-owned tests are sufficient for the observed pagination case.

## Consequences

Existing action inputs remain optional. Release checks need local Git history and the intended checked-out source. Current generated integrations need a refresh to consume the new planner context and selector option. Visibility/text assertions are a minimum guard against empty smoke runs, not proof that all changelog claims are covered. GitHub-hosted execution and external planner behavior still need their own evidence.
