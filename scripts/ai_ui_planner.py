"""Provider adapters for the app-owned planner; Python standard library only."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Mapping


EFFORTS = {
    "openai": ("none", "minimal", "low", "medium", "high", "xhigh", "max"),
    "anthropic": ("low", "medium", "high", "xhigh", "max"),
    "openai-compatible": ("none", "minimal", "low", "medium", "high", "xhigh", "max"),
}
KEY_NAMES = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


class PlannerError(ValueError):
    """Invalid configuration, provider failure, or unusable provider response."""


@dataclass(frozen=True)
class PlannerConfig:
    provider: str
    model: str
    effort: str
    api_key: str = field(repr=False)
    base_url: str = ""
    max_output_tokens: int = 16384


def load_config(environment: Mapping[str, str] | None = None) -> PlannerConfig:
    env = os.environ if environment is None else environment
    provider = env.get("AI_UI_PLANNER_PROVIDER", "").strip().lower() or "openai"
    if provider not in EFFORTS:
        raise PlannerError(f"Unknown planner provider; choose {', '.join(EFFORTS)}.")
    # The vendor-specific model alias remains valid only on the OpenAI path.
    model = env.get("AI_UI_PLANNER_MODEL", "").strip()
    if not model and provider == "openai":
        model = env.get("AI_UI_OPENAI_MODEL", "").strip() or "gpt-5-mini"
    if not model or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]*", model):
        raise PlannerError(f"Set AI_UI_PLANNER_MODEL to a valid model ID for {provider}.")
    effort = env.get("AI_UI_PLANNER_EFFORT", "").strip().lower()
    if effort == "default":
        effort = ""
    if effort and effort not in EFFORTS[provider]:
        raise PlannerError(
            f"Unsupported effort for {provider}; choose default, {', '.join(EFFORTS[provider])}. "
            "Individual models may support fewer levels."
        )
    base_url = env.get("AI_UI_PLANNER_BASE_URL", "").strip().rstrip("/")
    if provider == "openai-compatible":
        try:
            parsed = urllib.parse.urlsplit(base_url)
            parsed.port  # Validate the port before constructing a request.
        except ValueError:
            raise PlannerError("AI_UI_PLANNER_BASE_URL is not a valid API base URL.") from None
        if (
            not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment
            or any(character.isspace() for character in base_url)
            or parsed.scheme not in {"http", "https"}
            or (parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"})
        ):
            raise PlannerError(
                "openai-compatible requires AI_UI_PLANNER_BASE_URL with HTTPS "
                "(HTTP is allowed for loopback hosts only), without credentials, query, or fragment."
            )
    elif base_url:
        raise PlannerError("AI_UI_PLANNER_BASE_URL applies only to openai-compatible.")
    key_name = KEY_NAMES.get(provider, "AI_UI_PLANNER_API_KEY")
    api_key = env.get("AI_UI_PLANNER_API_KEY", "").strip() or env.get(key_name, "").strip()
    if not api_key and provider != "openai-compatible":
        raise PlannerError(f"{key_name} or AI_UI_PLANNER_API_KEY is required for {provider}.")
    if any(ord(character) < 32 or ord(character) == 127 for character in api_key):
        raise PlannerError("Planner API credentials must be a single line without control characters.")
    try:
        max_tokens = int(env.get("AI_UI_PLANNER_MAX_OUTPUT_TOKENS", "") or "16384")
    except ValueError as exc:
        raise PlannerError("AI_UI_PLANNER_MAX_OUTPUT_TOKENS must be a positive integer.") from exc
    if max_tokens <= 0:
        raise PlannerError("AI_UI_PLANNER_MAX_OUTPUT_TOKENS must be a positive integer.")
    return PlannerConfig(provider, model, effort, api_key, base_url, max_tokens)


def portable_schema(value: object) -> object:
    """Retain shape, move unsupported wire constraints into descriptions.

    All scenario constraints are still enforced by ai_ui_contract after decoding.
    Claude's raw-schema API rejects several constraints accepted by OpenAI.
    """
    if isinstance(value, list):
        return [portable_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    unsupported = {"minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"}
    result = {key: portable_schema(item) for key, item in value.items() if key not in unsupported}
    constraints = [f"{key}={item}" for key, item in value.items() if key in unsupported]
    if constraints:
        result["description"] = (str(result.get("description", "")) + " " + "; ".join(constraints)).strip()
    return result


def build_request(config: PlannerConfig, system_prompt: str, content: list[dict], schema: dict) -> urllib.request.Request:
    headers = {"Content-Type": "application/json"}
    if config.provider == "anthropic":
        converted = []
        for item in content:
            if item["type"] == "input_text":
                converted.append({"type": "text", "text": item["text"]})
            else:
                media, data = item["image_url"].split(",", 1)
                converted.append({"type": "image", "source": {
                    "type": "base64", "media_type": media.removeprefix("data:").removesuffix(";base64"), "data": data,
                }})
        output_config = {"format": {"type": "json_schema", "schema": portable_schema(schema)}}
        if config.effort:
            output_config["effort"] = config.effort
        payload = {
            "model": config.model, "max_tokens": config.max_output_tokens,
            "system": system_prompt, "messages": [{"role": "user", "content": converted}],
            "output_config": output_config,
        }
        url = "https://api.anthropic.com/v1/messages"
        headers.update({"x-api-key": config.api_key, "anthropic-version": "2023-06-01"})
    elif config.provider == "openai":
        payload = {
            "model": config.model, "instructions": system_prompt,
            "input": [{"role": "user", "content": content}],
            "text": {"format": {"type": "json_schema", "name": "ios_ui_scenario", "schema": schema, "strict": True}},
        }
        if config.effort:
            payload["reasoning"] = {"effort": config.effort}
        url = "https://api.openai.com/v1/responses"
        headers["Authorization"] = f"Bearer {config.api_key}"
    else:
        converted = [
            {"type": "text", "text": item["text"]} if item["type"] == "input_text"
            else {"type": "image_url", "image_url": {"url": item["image_url"]}}
            for item in content
        ]
        payload = {
            "model": config.model,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": converted}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "ios_ui_scenario", "schema": portable_schema(schema), "strict": True,
            }},
        }
        if config.effort:
            payload["reasoning_effort"] = config.effort
        url = config.base_url + "/chat/completions"
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
    return urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")


def decode_response(provider: str, payload: dict) -> dict:
    if not isinstance(payload, dict) or payload.get("error"):
        raise PlannerError(f"{provider} returned an invalid response or provider error.")
    if provider == "openai":
        if payload.get("status", "completed") != "completed":
            raise PlannerError("openai response did not complete; no scenario was accepted.")
        blocks = [block for item in payload.get("output", []) if item.get("type") == "message" for block in item.get("content", [])]
        if any(block.get("type") == "refusal" for block in blocks):
            raise PlannerError("openai refused the planning request.")
        parts = [block.get("text", "") for block in blocks if block.get("type") == "output_text"]
    elif provider == "anthropic":
        if payload.get("stop_reason") != "end_turn":
            raise PlannerError(
                "anthropic response did not finish with end_turn (refusal, token limit, or other stop); "
                "no scenario was accepted. For token limits, adjust AI_UI_PLANNER_MAX_OUTPUT_TOKENS."
            )
        parts = [block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text"]
    else:
        choices = payload.get("choices", [])
        if len(choices) != 1 or choices[0].get("finish_reason") != "stop":
            raise PlannerError("openai-compatible response did not finish with stop; no scenario was accepted.")
        message = choices[0].get("message", {})
        if message.get("refusal"):
            raise PlannerError("openai-compatible endpoint refused the planning request.")
        parts = [message.get("content", "")]
    if not parts or not all(isinstance(part, str) for part in parts) or not "".join(parts).strip():
        raise PlannerError(f"{provider} response contained no scenario text.")
    try:
        scenario = json.loads("".join(parts))
    except json.JSONDecodeError as exc:
        raise PlannerError(f"{provider} returned invalid scenario JSON.") from exc
    if not isinstance(scenario, dict):
        raise PlannerError(f"{provider} scenario must be a JSON object.")
    return scenario


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def generate_scenario(config: PlannerConfig, system_prompt: str, content: list[dict], schema: dict) -> dict:
    request = build_request(config, system_prompt, content, schema)
    try:
        # Never forward model credentials or repository context to a redirect.
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return decode_response(config.provider, payload)
    except urllib.error.HTTPError as exc:
        # Provider bodies may echo prompts or credentials. Surface the status and
        # selected configuration without copying those bodies into shared logs.
        raise PlannerError(
            f"{config.provider} request failed: HTTP {exc.code}; model={config.model}, "
            f"effort={config.effort or 'default'}. Check credentials, model access, "
            "and model/endpoint support for effort, images, and structured outputs."
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PlannerError(f"{config.provider} request failed or returned invalid JSON ({type(exc).__name__}).") from None
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise PlannerError(f"{config.provider} returned a malformed response ({type(exc).__name__}).") from None


if __name__ == "__main__":
    try:
        config = load_config()
        print(f"Planner: provider={config.provider}, model={config.model}, effort={config.effort or 'default'}")
    except PlannerError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
