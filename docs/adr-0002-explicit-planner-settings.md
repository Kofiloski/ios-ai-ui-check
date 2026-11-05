---
summary: Keep provider adapters in the generated app planner and expose explicit provider, model, and effort selection.
read_when:
  - Adding planner providers or reasoning-effort options
  - Changing planner configuration defaults or the public action boundary
---

# Explicit planner settings

Date: 2026-11-05. Status: Accepted.

## Context and constraints

The user requested provider, model, and effort selection, prioritizing Anthropic. The released action already delegates planning to an app-owned command, but its generated planner calls OpenAI and the local helper requires `OPENAI_API_KEY` even for replacement planners. That makes the default integration vendor-specific. The public executor must remain provider-independent, preserve existing OpenAI integrations, and validate every generated scenario before XCTest execution.

## Decision

Expose optional `planner-provider`, `planner-model`, and `planner-effort` inputs on the action/reusable workflow and matching local flags/environment settings. Add a Python standard-library adapter copied into the app scaffold, supporting native Anthropic Messages, existing OpenAI Responses, and an explicitly configured OpenAI-compatible Chat Completions endpoint. Keep custom planner commands available and pass these settings through without imposing vendor-specific validation in the public action.

Preserve the OpenAI provider/model defaults and legacy model/normalizer aliases. Require explicit model IDs for other providers. Omitted/default effort uses the provider's model default; explicit effort is sent using the provider's documented field. Fail unsupported adapter values locally and surface model-specific API rejections without silently changing the user's choice. Do not maintain a speculative model catalog. Initial native-provider work prioritizes Anthropic; a native Gemini adapter is deferred.

Keep one wire shape, normalization path, and canonical runtime/app validation. Adapt schema constraints only where the provider wire format requires it, retaining local enforcement. Reject refusals and incomplete results. Keep credentials out of diagnostics, require explicit compatible endpoints, and disable HTTP redirects. Credential-free deterministic checks are unchanged.

## Alternatives considered

- Asking every user to write a custom planner preserves extensibility but does not satisfy supported provider selection.
- Sending every provider through a nominally compatible API obscures Anthropic's native effort and structured-output behavior.
- Adding an SDK/router dependency introduces runtime installation and maintenance that the existing standard-library requests do not need.
- Translating all effort names into token budgets invents equivalence between provider semantics. Preserve documented provider values instead.

## Consequences

Consumers need an explicit scaffold refresh and an action revision containing the new inputs; installed skill guidance alone cannot upgrade them. Provider/model/effort combinations remain subject to actual model and endpoint capabilities. Fixture and loopback tests establish integration behavior, while live provider calls and hosted workflow runs remain separate evidence. See [planner configuration](planner-configuration.md) for credentials, usage, limits, and official sources.
