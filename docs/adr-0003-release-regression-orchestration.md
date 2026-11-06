---
summary: Separate release discovery, credentialed generation, native execution and durable history while reusing JSON XCTest scenarios.
read_when:
  - Changing release orchestration, credentials or history storage
  - Deciding whether baseline passes prove diff-driven test generation
---

# Release regression orchestration

Date: 2026-11-06. Status: Accepted.

## Context and constraints

Three popular-app forks passed fixed native scenarios. Those runs bypassed the
planner, even when Proton collected release context. They did not demonstrate
the requested diff → new UI tests → execution → release history flow. The user
confirmed JSON scenarios executed by XCTest as the generated test format.
No model API secret is configured in the forks; live model proof is unavailable.
Build scripts from upstream releases execute code, so they must not receive the
provider secret or the report publisher's write token.

## Decision

Add caller-owned stable iOS tag profiles and an opt-in scheduled reusable
workflow. Pin explicit release commits and preserve ADR 0001's strict checkout
contract. Reuse the provider adapters and existing native JSON interpreter.
Generate a bounded suite with changed-file claims and explicit uncovered files;
run each case independently and verify actual native test counts. Keep fixed
baselines separately named. Missing/unsupported input produces blocked/failing
evidence without a fallback passing scenario.

Separate native build/inspect, credentialed planning, native execution and
write-enabled history jobs. Archive immutable attempt assets on the fork and
retain a discovery queue that catches multiple releases and later hotfixes.
Bootstrap only the latest pair; older pairs require deliberate replay. Advance
the queue after each published attempt to avoid an unsupported old release
starving new ones. Manual replay retries blocked attempts after repair.

## Alternatives

- Treating provided-scenario passes as generation proof: rejected; the model
  never ran and no new diff-specific test was produced.
- Generating Swift source per release: not selected by the user; the constrained
  JSON interpreter reuses the existing app-side build and avoids compiling model
  output as arbitrary source.
- Keeping credentials and app builds in one job: rejected because upstream
  scripts could persist into the credentialed step.
- Actions artifacts alone: insufficient for historical reporting because they
  expire. Committing videos/result bundles into source branches would grow Git
  history; immutable report release assets are used instead.

## Consequences

Native products must transfer between jobs, which adds runtime and storage.
Historical toolchain/harness compatibility remains an explicit limitation.
Model coverage claims require review; valid schemas and passing assertions do
not prove complete release coverage. API credentials and scheduling remain
maintainer configuration. This implementation does not establish a live model
generation pass without those credentials.
