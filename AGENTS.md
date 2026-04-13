# Repo Notes

- Keep the public action provider-agnostic. Do not hard-code one AI vendor into the core executor unless there is a clear product decision.
- Keep app-specific launch, seeding, and assertion logic out of this repo. That belongs in the app repo's runner script.
- Prefer small shell and JSON-schema based changes over adding a heavier runtime unless there is a concrete need.
- Update `README.md` and `docs/*.md` when the runner contract, scenario schema, or execution model changes.
