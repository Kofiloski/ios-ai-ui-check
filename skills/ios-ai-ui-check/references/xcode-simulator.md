# Native Xcode Simulator checks

Use for local interaction and visual verification through Apple's Xcode agent tools. Xcode 27 added Simulator boot, app installation/launch, synthesized touch input, and screenshot capture. Availability depends on the connected Xcode and the tools actually exposed to the agent; having Xcode installed or a preview tool alone is insufficient.

## Discover the available capabilities

1. Check the selected developer directory and Xcode version with `xcode-select -p` and `xcodebuild -version`. If command line tools or another Xcode are selected, use a command-scoped `DEVELOPER_DIR` pointing to the intended installed Xcode; do not change the machine's global selection for a check.
2. Discover the session's Xcode tools and read their schemas. Confirm which tools can select a workspace/scheme/destination, build, boot, install/launch, send input, and capture screenshots. Do not guess tool names, parameter names, gesture support, or accessibility-tree capabilities from another MCP server's API.
3. Confirm the project, scheme, build configuration, runtime, and explicit Simulator identifier before launching. Reuse the app's existing launch arguments, environment, and data setup; do not erase a Simulator or overwrite user data to obtain a clean state.

For an agent inside Xcode, use its already available tools. For an external agent, Apple's documented setup is to open the project in Xcode, enable **Xcode > Settings > Intelligence > Allow external agents to use Xcode tools**, and connect the client to the stdio command `xcrun mcpbridge`. Respect existing connection permissions. Configure a missing connection only when requested or authorized; otherwise report the setup needed and use an existing runner if available. This skill does not require installing a third-party MCP server or an input-injection dependency.

If Xcode cannot launch, the bridge cannot connect, access is denied, or required tools are missing, report the observed failure. Do not enable headless access, broaden permissions, or reinstall Xcode as part of an ordinary UI check.

## Observe, act, verify

1. Define the starting state, shortest user path, and visible outcome to check. Build the current app, install it, and launch it on the selected Simulator through the available tools. Check tool results before proceeding.
2. Capture and inspect the starting screenshot. Confirm that the intended screen is visible and ready. If an inspection tool is available, use its actual output to identify controls; otherwise use the screenshot.
3. Send the next supported touch/input action and capture the resulting state. For coordinate input, use the tool's documented coordinate space and the current screenshot's dimensions, scale, orientation, and device. Do not reuse coordinates after navigation or layout changes without inspecting again.
4. Wait for the expected visible state using bounded polling or the tool's completion signal. Avoid blind action sequences and fixed delays as proof of readiness. If a target is obscured, an action fails, or progress stalls, inspect the new screenshot and logs before retrying; stop repeated failures with the last useful evidence.
5. Compare the final state with the requested outcome. Save available screenshots and a concise action record with the build/source revision, Xcode version, scheme/configuration, Simulator identifier/runtime, locale/appearance, launch setup, and observed versus expected behavior. Redact secrets and personal data from shared evidence.

Use an app-owned test or scenario when repeatable coverage is needed. Native input can help discover the path, but a successful coordinate tap does not establish a stable accessibility contract. For an identifier/type failure, inspect with the failing automation tool and replay that exact test after the patch. Keep failures as failures rather than replacing a broken test with a screenshot-only check.

## Evidence boundaries

- Distinguish a SwiftUI preview from a running app, and observed UI behavior from an automated assertion.
- Native checks need only the evidence their tools actually produce. Keep the reusable action's required artifact contract unchanged for CI runs.
- Simulator interaction does not verify signed-device behavior, real purchases, hardware/sensor behavior, or App Store approval.

## Apple sources

- [Xcode 27 release notes](https://developer.apple.com/documentation/xcode-release-notes/xcode-27-release-notes), Coding Intelligence, issue 175179787: native Simulator controls.
- [Giving external agents access to Xcode](https://developer.apple.com/documentation/xcode/giving-external-agents-access-to-xcode): MCP bridge and connection setup.

Consult the selected Xcode's tool schemas and current release notes when behavior differs; this reference is not a fixed tool catalog.
