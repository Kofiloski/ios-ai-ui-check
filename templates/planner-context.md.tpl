__SCAFFOLD_HEADER_MARKDOWN__
# AI UI Planner Context

Update this file with app-specific guidance for the default AI planner.

## App

- Scheme: __SCHEME_MARKDOWN__
- Provided scenario override path: __SCENARIO_PATH_MARKDOWN__

## Preferred deterministic launch

- List the exact launch arguments or environment variables that make the app predictable in CI.
- Include the exact key names and example values. Avoid placeholders.
- Source-discovered environment key names alone are not enough. If the planner should use a launch environment variable, document the exact key-value pair here.
- If the app has automation routes, note them here.
- If the app has debug-only seeded data, note how to enable it here.
- If the app has multiple possible startup roots, explain how to force the preferred one.
- If a UI target only appears in a conditional state such as an empty state, sheet, modal, or paywall, document the exact launch setup or route that guarantees that state.

## Preferred flow

- Describe the primary UI flow the planner should favor.
- Call out the most stable accessibility identifiers or labels for that flow.
- Prefer stable generic entry points over conditional empty-state CTAs when both exist, unless the launch configuration guarantees the empty state.
- Document any intermediate menus, sheets, dialogs, or chooser actions between a generic CTA and the final destination. Include the specific follow-up identifiers the planner should tap.
- Mention the final state that should be asserted.
- If AI planning is not reliable without app-specific launch setup, say so clearly and prefer the checked-in scenario override.

## Avoid

- Real credentials or production-only flows
- Flaky gestures, long waits, or animations
- Network-dependent behavior unless the app has reliable mocks or seeded data
