---
summary: Select an Anthropic, OpenAI, or compatible planner with explicit model and effort settings.
read_when:
  - Selecting a planner provider, model, or reasoning effort
  - Configuring Claude planning locally or in GitHub Actions
  - Diagnosing provider credentials, unsupported effort, or structured output failures
---

# Planner configuration

Provider/model/effort selection is available from `v0.6.0`. Generate or explicitly refresh the app scaffold from that release and pin the action to `v0.6.0` or a reviewed newer commit. Earlier integrations, including `v0.5.0`, need this explicit upgrade. Installing a skill does not upgrade the app's generated scripts or its pinned action.

The public action forwards configuration to the app-owned planner command. Only the generated `scripts/ai_ui_planner.py` adapter makes model requests; XCTest execution and scenario validation remain provider-independent. Custom planner commands keep their existing contract and receive the same settings. These options configure planner API calls; they do not switch the model or effort of the coding-agent session running the skills.

## Local selection

With `ANTHROPIC_API_KEY` already set in the environment:

```bash
./scripts/local-ai-ui-check.sh \
  --provider anthropic \
  --model claude-sonnet-4-6 \
  --effort high \
  --goal "Verify settings persist after reopening the app"
```

`--planner-provider`, `--planner-model`, and `--planner-effort` are equivalent aliases. Flags override environment defaults. The old `--planner-model` option remains supported.

| Setting | Environment | Default |
| --- | --- | --- |
| Provider | `AI_UI_PLANNER_PROVIDER` | `openai` |
| Model | `AI_UI_PLANNER_MODEL` | `gpt-5-mini` for OpenAI; explicit for other providers |
| Effort | `AI_UI_PLANNER_EFFORT` | Unset or `default`: omit the API field and use the model's default |
| Compatible API base URL | `AI_UI_PLANNER_BASE_URL` | Required for `openai-compatible`; include `/v1` when the server uses it |

For existing OpenAI setups, `AI_UI_OPENAI_MODEL` remains a fallback when the provider is OpenAI and `AI_UI_PLANNER_MODEL` is unset. Model IDs are passed exactly as supplied; the adapter never substitutes another model.

## Providers and effort

| Provider | Credentials | Effort field | Accepted adapter values |
| --- | --- | --- | --- |
| `anthropic` | `ANTHROPIC_API_KEY` | Messages API `output_config.effort` | `low`, `medium`, `high`, `xhigh`, `max` |
| `openai` | `OPENAI_API_KEY` | Responses API `reasoning.effort` | `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max` |
| `openai-compatible` | Optional `AI_UI_PLANNER_API_KEY` | Chat Completions `reasoning_effort` | Same adapter values as OpenAI; endpoint support varies |

`AI_UI_PLANNER_API_KEY` can supply a provider-neutral credential and takes precedence over the selected provider's named key. OpenAI and Anthropic require a key; a compatible local server may not. The compatible adapter never borrows an OpenAI or Anthropic key implicitly.

These are API vocabulary checks, not a frozen model support catalog. Individual models support fewer effort levels and different image/schema capabilities. Unsupported provider/effort names fail locally; model-specific rejections fail with the HTTP status and selected settings. There is no automatic downgrade, provider switch, or retry that removes effort or images. Equal effort names do not imply equal token use, price, or quality across providers. Configure a compatible endpoint only when its documented capabilities satisfy this request; some servers may ignore optional fields.

Claude requests use native Messages authentication, text/image blocks, structured JSON output, and the selected effort. Thinking blocks are excluded from scenario parsing. Only `stop_reason: end_turn` is accepted; refusals, truncated output, and other stops fail even if a partial response contains parseable JSON. `AI_UI_PLANNER_MAX_OUTPUT_TOKENS` sets the positive Claude output-token cap (default `16384`); raise it deliberately if the chosen model/effort runs out of output budget. It is a separate control from effort.

The adapters preserve one planner shape. Claude and compatible requests move unsupported numeric/string wire constraints into descriptions; the canonical local validator still enforces the complete runtime contract and app-specific identifier/launch rules. A schema-shaped response alone does not establish a valid scenario or a passing UI check.

## Workflow selection

With a scaffold generated or refreshed from `v0.6.0`:

```yaml
- uses: Kofiloski/ios-ai-ui-check@v0.6.0
  with:
    planner-command: ./scripts/plan-ai-ui-scenario.sh
    planner-provider: anthropic
    planner-model: claude-sonnet-4-6
    planner-effort: high
    planner-goal: Verify settings persist after reopening the app.
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

The reusable workflow accepts the same four configuration inputs, including optional `planner-base-url`. Its `planner-api-key` secret is exported as `AI_UI_PLANNER_API_KEY` and the configured `planner-api-key-env-name` (legacy default `OPENAI_API_KEY`). This preserves existing custom planners while allowing the generated Anthropic planner to consume the same secret without an OpenAI key. Configuration inputs override inherited `AI_UI_PLANNER_*` values when nonempty. Unset inputs preserve the environment values; use `default` to explicitly reset effort to the model's default.

The generated manual workflow exposes `planner_provider`, `planner_model`, `planner_effort`, and `planner_base_url`. PR runs can use repository variables `AI_UI_PLANNER_PROVIDER`, `AI_UI_PLANNER_MODEL`, `AI_UI_PLANNER_EFFORT`, and `AI_UI_PLANNER_BASE_URL`. Store credentials as repository secrets, never in those variables. Forked pull requests still do not receive repository secrets.

`planner-request.md` records requested provider/model/effort alongside the existing planning context. These values describe the request, not server-confirmed effective settings. Custom planners own their interpretation of these fields. Provider errors do not copy response bodies into shared logs because they can echo prompts or credentials.

## Compatible and deterministic paths

For a reviewed local server with vision and structured-output support:

```bash
./scripts/local-ai-ui-check.sh \
  --provider openai-compatible \
  --base-url http://localhost:11434/v1 \
  --model your-installed-vision-model \
  --effort default \
  --goal "Verify the primary flow"
```

The base URL is required and must use HTTPS, except HTTP on loopback hosts. URL credentials, query strings, and fragments are rejected. Provider requests do not follow redirects, avoiding transmission of credentials and context to a redirected destination. Other transports can remain in an app-owned custom planner command.

`--use-example-scenario` or `--scenario PATH` bypasses model planning and needs no provider credentials. The generated local helper also supports replacement app-owned planners without imposing an OpenAI-key check.

## Verification and sources

Tests cover request construction, effort forwarding/default omission, credentials, image payloads, Claude refusals/truncation, shared scenario validation, generated app scripts, and a real loopback HTTP roundtrip. Those checks do not establish live model access, model quality, or hosted GitHub execution. Live provider checks require an authorized credentialed call; do not advertise them as verified from fixtures alone.

Provider field mappings were checked against official documentation on November 5, 2026: [Anthropic effort](https://platform.claude.com/docs/en/build-with-claude/effort), [Anthropic structured output](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), [OpenAI reasoning](https://developers.openai.com/api/docs/guides/reasoning), and [Ollama's partial OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility).
