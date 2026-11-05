---
summary: Use native Simulator tools and scoped runtime diagnostics while preserving the app-owned runner and CI artifact contracts.
read_when:
  - Choosing between a local native check and a reproducible scenario
  - Diagnosing a local UI failure with logs, saved state, or runtime inspection
  - Updating the installable skill or synchronizing its toolkit copy
---

# Native Xcode checks

The installable `skills/ios-ai-ui-check/` bundle guides agents through local exploration and adoption of the reusable action. Its `references/xcode-simulator.md` contains the local procedure. Native tools belong to the connected Xcode session; the GitHub Action does not gain an MCP dependency or execute native agent sessions as CI scenarios.

For local exploration, discover the actual tool schemas, confirm the project, scheme, and Simulator, reuse existing launch/data setup, and inspect the state between input actions. Preserve observed outcomes and the evidence the tools actually produce. If native capabilities are unavailable, use existing app-local automation or report the verification gap. Adding a UI-test target or planner is unnecessary for a local-only request.

For an unfamiliar app, the skill's `references/app-build-preflight.md` covers scheme and shell-script side effects, public dependency preparation, dependency extraction and build-space peaks, platform selection, and reuse of existing tests. A destination does not constrain scripts that enumerate every booted Simulator. A missing private prerequisite must be attributed to the target that consumes it, and documented public fallbacks remain visible in the build provenance. Keep setup/build failures distinct from UI assertions and verify that a filtered test run executed the intended tests.

When the cause remains unclear, `references/simulator-diagnostics.md` adds a scoped diagnostic loop: correlate the same reproduction with bounded app logs, relevant persisted state, or focused debugger inspection. Prefer available Xcode, `simctl`, and app-owned helpers. Keep raw state out of planner/upload directories, label instrumentation, and verify the original path without hooks. No Simulator jailbreak, injected runtime dependency, or new CI artifact requirement is introduced. Connection/access failures remain explicit verification gaps rather than reasons to reset user data or change host permissions.

Xcode/XCTest and Apple's command-line tools are the supported local baseline. External inspectors, third-party MCP servers, and companion CLIs are optional and must be discovered before use. Native Xcode tools may return workflow guidance that routes through an Xcode-bundled skill, including a required device-interaction subagent; follow the actual connected tool's guidance only when the host supports that mode. If it does not, use the available XCTest path or disclose the limitation. Tool installation and permission configuration are separate from an ordinary UI verification request.

When repeatable coverage is required, preserve the path and expectations in the app's scenario or XCUITest contract and replay through that runner. A screenshot does not establish a correct XCTest identifier/type, passing backend behavior, or a successful automated assertion. Keep the CI action's existing artifact requirements unchanged.

This repository is the canonical source for the installable skill. `ios-release-quality-toolkit` embeds a separate copy. Compare and synchronize instructions, references, metadata, and action refs when releasing either bundle; a release does not upgrade previously installed skills or existing generated app scaffolds.

For changes to the skill, run the skill-creator validator and check local reference links alongside `./scripts/check-release-readiness.sh <tag>` and `docs-list . --strict`. Live native Simulator behavior needs its own connected-Xcode verification; static checks and documentation review do not establish it.
