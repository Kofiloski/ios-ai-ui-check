# Examples

These workflows assume [`scripts/scaffold-app-repo.py`](../scripts/scaffold-app-repo.py) has already added the app-owned runner, UI test target, and scenario.

## Deterministic PR Check

Copy [`deterministic-pr-check.yml`](deterministic-pr-check.yml) to `.github/workflows/ios-ui-check.yml` in the app repo. It calls the reusable workflow with the scaffolded checked-in scenario, so it needs no model provider or API key.

The compact example runs on every pull request. Keep the scaffold-generated label gate when UI checks should remain opt-in while the flow is still expensive or maturing.

Review `.github/ai-ui/verify-primary-flow.json` before relying on the check. The generated starter only launches and captures the initial UI until the app repo adds its own stable interactions and assertions.

The example uses the immutable `v0.6.0` release. A full commit SHA provides the strongest source pin; the moving `v0` tag opts into compatible updates.

## AI-Planned Variant

For goal-driven planning, replace `provided-scenario-path` with the app-owned planner inputs:

```yaml
    with:
      planner-command: ./scripts/plan-ai-ui-scenario.sh
      planner-provider: anthropic
      planner-model: claude-sonnet-4-6
      planner-effort: high
      planner-goal: Verify the most likely user-visible flow affected by this PR.
    secrets:
      planner-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
```

The wrapper exposes this secret as `AI_UI_PLANNER_API_KEY` for the generated Claude planner and preserves its legacy/custom environment export. Select `openai` and an OpenAI model/key to use the existing Responses adapter, or configure an `openai-compatible` endpoint. The reusable action itself does not call a model API. Existing app integrations need an explicit scaffold refresh for the `v0.6.0` adapters; see [planner configuration](../docs/planner-configuration.md).
