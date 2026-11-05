# Preparing an unfamiliar app

Use this reference when the app's existing build and test setup has not yet been exercised in the current environment.

## Trace the selected build and test path

Read the selected scheme's build/test preactions and postactions, test plan, target shell phases, and the scripts they invoke before running them. A Simulator destination only scopes Xcode's destination: a shell script can still modify every booted Simulator, install global tools, or format source files.

If an action affects unrelated devices or host setup, prepare an app-owned local scheme or runner that scopes the operation to the selected destination. Preserve required dependency preparation and code generation explicitly, and record deviations from the upstream scheme. Do not remove a required build step merely to obtain a green result.

Keep Xcode selection command-scoped with `DEVELOPER_DIR`. Confirm the actual test action as well as the scheme name; a Swift package's library scheme may build while its package scheme owns the tests. Match the destination to the imported frameworks: a package's declared macOS support does not prove its current sources compile for the host.

## Establish the public build prerequisites

Separate optional inspection utilities from dependencies the app actually needs. Use existing installed tools for equivalent setup where possible. A downloader that offers to install a convenience CLI does not make that CLI a toolkit prerequisite. Preserve the upstream version and checksum when preparing a public binary dependency with another downloader.

If public package downloads stall, distinguish network activity from credential lookup using the build log and a bounded process observation. Check the installed `xcodebuild -help` before choosing a command-scoped authorization provider. For example, `-packageAuthorizationProvider netrc` can avoid an unnecessary Keychain lookup for a public dependency graph. This is conditional setup guidance; private dependencies may need their existing credential store. Do not change host Keychain permissions to unblock ordinary public downloads.

Trace private prerequisites to their consuming target. A missing internal UI-test script can block that test target without proving the main app is unbuildable. Use a documented public fallback where available and record its effect on the result, such as a system-font fallback changing a screenshot baseline. Do not invent credentials, replace production logic with stubs, or present a modified build as identical to the upstream release.

Inspect submodules, LFS references, generated assets, and bootstrap scripts for the selected path. Fetch required inputs, pin their provenance, and avoid downloading unrelated snapshot corpora or executing a moving remote bootstrap script without reviewing it.

## Choose a focused verification path

Inspect existing tests, launch arguments, fixtures, and accessibility queries before creating a target. Prefer a meaningful existing flow selected with `-only-testing` when it exercises the requested behavior. Avoid inheriting release, deployment, or notification workflows just to run a local test.

Check disk headroom before dependency resolution and builds. On a constrained host, run apps sequentially and retain logs, source revisions, integration diffs, and `.xcresult` evidence before arranging cleanup of regenerable products. Existing cleanup authorization and the host's cleanup rules still apply; do not remove active runtimes, source edits, or release evidence to make a test fit.

Allow for peak usage from repository checkouts, compressed downloads, temporary extraction, expanded binary frameworks, and build products. Source checkout size alone is insufficient, and a sequential schedule still needs room for one app's peak. When an earlier attempt exhausted storage, use a bounded disk-space monitor for the retry and record a storage stop separately from compiler errors or UI assertion failures. Keep unknown size estimates explicit rather than promising that a fixed amount of free space will fit every app.

Report setup, build, unit-test, and UI-test outcomes separately. Confirm that the selected tests actually executed; a successful empty test selection is not coverage. Preserve an initial platform/setup failure alongside the corrected replay. A passing package test does not establish that the app or its UI runner works.
