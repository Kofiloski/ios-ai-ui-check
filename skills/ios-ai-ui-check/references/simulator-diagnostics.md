# Simulator diagnostics

Use when a UI reproduction needs evidence about execution, saved state, or view exposure. Start with existing Xcode tools and app-owned inspect/replay helpers. The Simulator runs iOS userspace on the Mac kernel; it does not need a conventional iPhone jailbreak for app debugging or container inspection.

Treat third-party utilities and companion CLIs as optional integrations. Check availability before suggesting their commands; neither this skill nor a user's machine is assumed to provide them. Prefer Xcode/XCTest and Apple's installed command-line tools. If a specialized state reader is unavailable, disclose that specific diagnostic gap while completing the checks the available tools support.

## Establish the reproduction

Record the app source revision, build configuration, scheme, bundle identifier, executable name, explicit Simulator UDID/runtime, locale, appearance, launch setup, and reproduction start/end times with timezone. Confirm the installed build is the one being investigated. Use the same device and app state for screenshots, logs, and state reads; do not mix artifacts from separate runs without labeling them.

Check the selected developer directory and connected tool capabilities as described in [xcode-simulator.md](xcode-simulator.md). Use a command-scoped `DEVELOPER_DIR` if needed. Discover CLI options with the installed `simctl help` rather than assuming another Xcode version's behavior. A service connection failure or access denial is a tooling gap, not proof that the app or runtime is broken. Record the exact failure; do not reset devices, alter global Xcode selection, or broaden host permissions to obtain diagnostics.

Capture the failure on the unmodified build before adding logging, attaching hooks, or changing data. Choose the next diagnostic to distinguish concrete alternatives, such as a control not receiving input, validation rejecting it, a save failing, or the screen displaying stale state.

## Logs around the failed action

Prefer the existing test log, app console, or `.xcresult` before collecting more. For a fresh reproduction, retain a short start/end window and filter by the actual executable name or known app subsystem. For example, after resolving these values from the selected build and installed tools:

```bash
xcrun simctl spawn "$SIMULATOR_UDID" log show \
  --start "$REPRO_START" --end "$REPRO_END" \
  --style compact --predicate 'process == "ResolvedExecutableName"'
```

Replace the predicate's executable with the real `CFBundleExecutable`; a bundle identifier is not necessarily a process name. Use the date/time format accepted by the installed `log help show`. Retain stderr and exit status, and distinguish an empty successful query from a failed query. Some app `print` output may be present only in the runner or launch console; absence from unified logging does not prove a method never ran.

If a live stream is necessary, use a bounded capture around one reproduction and stop it afterwards. Avoid device-wide log dumps. Keep relevant errors and timing, redact credentials and personal content, and do not enable private-data logging to fill a gap.

## Inspect persisted app state

Trace the source to the store actually used by this flow before choosing a file. Distinguish in-memory state, preferences, app-container files, app-group stores, keychain, and remote state. Resolve current container paths; do not reuse a container UUID from another install:

```bash
xcrun simctl get_app_container "$SIMULATOR_UDID" "$APP_BUNDLE_ID" data
```

Resolve an app-group container only when the target's entitlements and persistence code show it is relevant, using the installed command's documented options. Restrict reads to the relevant store/key/record. Do not recursively collect the app's entire container or unrelated apps' data.

For SQLite, Core Data, or SwiftData, obtain a consistent snapshot before querying. Prefer an app-owned export or SQLite's online backup API with a read-only source connection. If copying files instead, stop the relevant writers through the existing workflow and preserve any matching WAL/SHM files; copying only a live main database can omit committed changes. Keep raw snapshots local, outside upload/planner directories, and report the small redacted query result that supports the finding. Discover the schema from that snapshot rather than assuming Core Data table or column names. Do not edit the live database or apply migrations as a diagnostic.

Record when the snapshot was taken relative to the UI action and any relaunch. For a persistence claim, check the specific record through the app, inspect the corresponding stored values when available, and relaunch through the normal path. A success toast or an in-memory view is insufficient. A local record does not establish that a server or iCloud accepted a change.

## View and runtime inspection

Use the failing automation tool's accessibility tree or focused XCTest query to inspect identifier, type, uniqueness, and reachability. Xcode's view debugger and LLDB can help explain the underlying view/state, but a UIKit view hierarchy is not the XCTest accessibility tree or a complete representation of SwiftUI's logical structure.

If logs and state reads leave a specific question unresolved, attach the existing debugger to the selected app process. Prefer one breakpoint, stack trace, or focused variable inspection over a heap dump. Record debugger pauses and added instrumentation because they can change timing. Debugger expressions can execute code and mutate state; use existing inspection helpers or narrowly understood reads. Do not call an action directly or force a return value and count that as a passing UI path.

For an explicitly requested instrumentation session, first verify the target device/runtime, app deployment target, tool versions, and the app scope. Frida can support deeper inspection on a compatible jailbroken device, and Simulator tweak-injection tools exist, but neither is a default dependency. Do not jailbreak a device, install packages, modify the Simulator runtime, or weaken host security as part of ordinary diagnostics. Use already available tooling only when authorized, label the instrumented run, and reproduce the outcome through the original path without the hooks before treating the issue as fixed.

## Close the evidence loop

Report the expected result, observed result, relevant timestamps, commands/tools, and exact artifacts inspected. Separate supported conclusions from remaining hypotheses. If identifiers or launch state changed, inspect with the original automation client and replay the exact failure path. If repeatable coverage is requested, preserve the assertion in the app-owned test/scenario.

Local diagnostics do not require a CI manifest or `.xcresult` that the tools did not produce. Additional diagnostics do not change the reusable action's existing artifact contract. Redact shared excerpts before upload and reference raw local state separately. Keep unavailable logs, unreadable stores, missing inspection tools, and blocked replays explicit; do not turn missing evidence into a pass.

Simulator and instrumented-device results do not establish physical-device performance, sensor behavior, production purchases, entitlement enforcement, or App Store approval.

## Sources

- [Apple: Getting the Most Out of Simulator](https://developer.apple.com/videos/play/wwdc2019/418/) explains Simulator architecture and debugging differences.
- [Apple: Running your app on simulated or physical devices](https://developer.apple.com/documentation/xcode/running-your-app-on-simulated-or-physical-devices) explains debugging and physical-device verification.
- [SQLite Online Backup API](https://www.sqlite.org/backup.html) describes consistent database snapshots.
- [Frida: iOS](https://frida.re/docs/ios/) documents device instrumentation modes.
- [simject](https://github.com/akemin-dayo/simject) documents Simulator tweak injection; check compatibility before adopting it.
