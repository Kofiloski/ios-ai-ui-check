---
name: ios-ai-ui-check
description: Run local iOS Simulator UI checks and diagnose failures with native Xcode tools, logs, and app-state inspection, or add, operate, and debug reproducible GitHub Actions checks with ios-ai-ui-check. Use for direct Simulator interaction, exploratory UI verification, deterministic XCUITest replay, app-owned runner or scenario setup, and planner, Simulator, runner, or artifact failures. Keep launch state, data, accessibility identifiers, interactions, and assertions in the app repository; keep the reusable action provider-agnostic.
---

# iOS AI UI Check

Use Xcode's native Simulator controls for focused local verification and the public `Kofiloski/ios-ai-ui-check` action for reproducible automation. Choose the mode that matches the requested evidence.

## Workflow

1. Read the target repository's instructions and existing automation. Identify the workspace/project, shared scheme, supported Simulator destination, launch/testing helpers, and any UI-test target. For an unfamiliar app or public-source checkout, read [references/app-build-preflight.md](references/app-build-preflight.md) before executing its setup or schemes.
2. Choose the mode that satisfies the request:
   - For local exploration, reproducing a visible bug, or checking a UI change, prefer Xcode 27 or later's native Simulator tools when exposed to this session. Read [references/xcode-simulator.md](references/xcode-simulator.md), discover the actual tool schemas, and run the focused interaction loop. A local check does not require scaffolding a UI-test target, planner, or GitHub workflow. If native tools are unavailable, use existing app-local automation; report the limitation if neither path is available.
   - When a failure needs explanation beyond the visible UI, read [references/simulator-diagnostics.md](references/simulator-diagnostics.md). Correlate the same reproduction with bounded app logs, relevant persisted state, or debugger observations. Use existing Xcode, `simctl`, and app-owned helpers first; a Simulator jailbreak or injection dependency is unnecessary for this workflow.
   - Prefer a checked-in scenario for required or security-sensitive CI.
   - Use a planner goal when exploratory coverage is useful and the app repo can explicitly control the context sent to its chosen provider.
   - When repeatable regression coverage is requested, preserve the observed path and expectations in the app's existing XCUITest or scenario contract, then replay through that runner.
3. For CI integration, read `references/adoption.md` before scaffolding or editing a workflow. The remaining integration steps apply to deterministic and planner modes.
4. Pin the public action to a release tag or commit SHA. Do not track `main` in stable CI.
5. Reuse existing focused app-owned tests and runners where they satisfy the requested behavior. When a new integration needs the upstream scaffold, run its dry-run first, review the proposed files, then generate them only within the target app repo.
6. Review the generated app-owned contract before running it:
   - deterministic launch arguments and environment values
   - safe fixtures, mocks, or test accounts
   - stable accessibility identifiers on the actual controls
   - focused assertions that prove the requested behavior
   - planner context that contains no secrets
7. Run the checked-in scenario locally before enabling a PR workflow. Treat Simulator availability, Xcode version, and shared-scheme failures as setup problems rather than planner problems.
8. Inspect `summary.md`, `manifest.json`, logs, screenshots, video, and `.xcresult` together. Do not report success from a status dot when the evidence contradicts it.
9. Keep fixes at the correct boundary:
   - reusable orchestration or artifact-contract defect -> fix `ios-ai-ui-check`
   - element lookup, wrong element type, identifier collision, or unreachable route -> use `$ios-ui-testability-contract` if available; otherwise inspect the failing runner's UI tree, patch the app-side control identifier/exposure or launch route, and replay the exact failing test/scenario. The companion skill is optional.
   - app launch, data, interaction, or assertion logic -> fix the app-owned runner

## Guardrails

- The supported local path uses Xcode's native tools or XCTest plus Apple's command-line tools. Discover capabilities at runtime. Do not assume AXe, XcodeBuildMCP, another MCP server, or companion CLIs are installed, and do not make them prerequisites. An optional utility being present is not a reason to prefer it over the supported path; if a diagnostic is unavailable, use the available Apple tools or report the gap.
- Do not move app-specific launch, seeding, UI interaction, or assertions into the reusable action.
- Do not add a hard-coded model provider to the action. Only the app-owned planner command may choose a provider.
- Never pass secrets through prompts, planner context, logs, scenarios, screenshots, or artifacts.
- Prefer `pull_request` when compiling and running pull-request code. Do not switch to `pull_request_target` to gain secret access.
- Start with manual or label-triggered runs. Make the check required only after launch state and identifiers are deterministic.
- For native local checks, record the observed result of each requested behavior. A screenshot supports a visual observation; it does not prove an accessibility identifier, XCTest element type, or backend outcome.
- Keep diagnostics scoped to the selected app and reproduction. Preserve user data, separate unmodified runs from instrumented runs, and keep sensitive state out of planner context and shared artifacts.
- For automated checks, do not promise visual correctness unless the app-owned scenario contains an explicit, reviewable assertion for it. Do not present a native interaction session as a passing CI scenario or invent `.xcresult`/manifest/video artifacts that were not produced.

## Completion evidence

Report:

- selected native local, deterministic, or planner mode and why
- Xcode version, scheme, Simulator runtime/device and identifier; action ref when applicable
- app-owned files added or changed
- native tools/actions used or exact local/CI command run, plus observed results
- artifact paths inspected
- diagnostic time window, state reads or instrumentation used, and how each observation supports the conclusion; unavailable diagnostics remain verification gaps
- any remaining app-specific contract or credential work
