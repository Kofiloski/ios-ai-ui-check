---
summary: Use native Xcode Simulator tools for local exploration while preserving the app-owned runner and CI artifact contracts.
read_when:
  - Choosing between a local native check and a reproducible scenario
  - Updating the installable skill or synchronizing its toolkit copy
---

# Native Xcode checks

The installable `skills/ios-ai-ui-check/` bundle guides agents through local exploration and adoption of the reusable action. Its `references/xcode-simulator.md` contains the local procedure. Native tools belong to the connected Xcode session; the GitHub Action does not gain an MCP dependency or execute native agent sessions as CI scenarios.

For local exploration, discover the actual tool schemas, confirm the project, scheme, and Simulator, reuse existing launch/data setup, and inspect the state between input actions. Preserve observed outcomes and the evidence the tools actually produce. If native capabilities are unavailable, use existing app-local automation or report the verification gap. Adding a UI-test target or planner is unnecessary for a local-only request.

When repeatable coverage is required, preserve the path and expectations in the app's scenario or XCUITest contract and replay through that runner. A screenshot does not establish a correct XCTest identifier/type, passing backend behavior, or a successful automated assertion. Keep the CI action's existing artifact requirements unchanged.

This repository is the canonical source for the installable skill. `ios-release-quality-toolkit` embeds a separate copy. Compare and synchronize instructions, references, metadata, and action refs when releasing either bundle; a release does not upgrade previously installed skills or existing generated app scaffolds.

For changes to the skill, run the skill-creator validator and check local reference links alongside `./scripts/check-release-readiness.sh <tag>` and `docs-list . --strict`. Live native Simulator behavior needs its own connected-Xcode verification; static checks and documentation review do not establish it.
