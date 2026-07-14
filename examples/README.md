# Examples

These workflows assume [`scripts/scaffold-app-repo.py`](../scripts/scaffold-app-repo.py) has already added the app-owned runner, UI test target, and scenario.

## Deterministic PR Check

Copy [`deterministic-pr-check.yml`](deterministic-pr-check.yml) to `.github/workflows/ios-ui-check.yml` in the app repo. It calls the reusable workflow with the scaffolded checked-in scenario, so it needs no model provider or API key.

The compact example runs on every pull request. Keep the scaffold-generated label gate when UI checks should remain opt-in while the flow is still expensive or maturing.

Review `.github/ai-ui/verify-primary-flow.json` before relying on the check. The generated starter only launches and captures the initial UI until the app repo adds its own stable interactions and assertions.

The example uses the immutable `v0.3.0` release. A full commit SHA provides the strongest source pin; the moving `v0` tag opts into compatible updates.

## AI-Planned Variant

For goal-driven planning, replace `provided-scenario-path` with the app-owned planner inputs:

```yaml
    with:
      planner-command: ./scripts/plan-ai-ui-scenario.sh
      planner-goal: Verify the most likely user-visible flow affected by this PR.
    secrets:
      planner-api-key: ${{ secrets.OPENAI_API_KEY }}
```

That secret name matches the generated OpenAI planner only. A replacement planner can use another provider by setting `planner-api-key-env-name` or by managing its credentials in the caller workflow. The reusable action itself does not call a model API.
