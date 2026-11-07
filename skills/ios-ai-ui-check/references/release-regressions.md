# Diff-driven release tests

Use this mode when the request is previous/new release comparison followed by
new targeted UI tests and a historical report. A fixed provided scenario proves
execution only, even if a release diff is collected alongside it.

Resolve and pin both upstream commits in the caller, applying the app-owned
harness to the exact new source. Keep iOS tag filters app-specific in multiapp
repositories. Preserve the complete diff and disclose any bounded model excerpt.
Do not silently substitute the current branch or the harness seed on failure.

Generate JSON scenarios for the existing native XCTest interpreter. Bind each
case to real changed files and a specific changed-behavior claim. Use reviewed
launch presets and meaningful assertions. Keep unreachable/authenticated,
hardware-only or unsupported changes explicitly uncovered; missing data does
not justify a guessed fixture or unrelated passing smoke check.

Run generated cases independently and inspect native results, media and logs.
Empty/skipped selection is not success. A model's claimed association with a
diff still needs review; schema validity alone cannot prove coverage quality.

The optional release orchestrator in the action repository separates upstream
build/inspection from credentialed planning and write-enabled report publication.
Do not collapse those trust boundaries. Durable per-release reports belong on
the fork, not upstream issue/notification workflows. Respect queue bootstrap and
explicit historical replay instead of launching a whole catalog accidentally.

Report these layers separately: selected comparison, generated cases, actual
native execution, uncovered changes, and durable publication. Fixture planning
responses, generic Swift compilation, baseline runs and live model generation
are distinct evidence. Missing provider credentials must block generation, never
fall back to a provided baseline and claim release-generation success. The new
orchestrator needs its own reviewed source pin; do not assume a prior published
action release contains it.

Before advertising regression detection, show an important unchanged assertion
failing on a known faulty version or an explicitly labelled seeded fault and
passing after correction. Keep fixture and harness differences reviewable.
Archive successful native proof beyond CI retention. A controlled baseline fault
demonstrates failure sensitivity; it does not establish live unattended planning.
Keep inactive integrations as pinned references instead of expanding recurring
maintenance before the flagship has complete evidence.
