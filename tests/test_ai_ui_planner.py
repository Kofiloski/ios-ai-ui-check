from __future__ import annotations

import json
import sys
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ai_ui_contract as contract
import ai_ui_planner as planner


SCENARIO = {"name": "A scenario", "steps": [{"action": "wait", "seconds": 0}]}
CONTENT = [
    {"type": "input_text", "text": "Verify settings"},
    {"type": "input_image", "image_url": "data:image/png;base64,cG5n"},
]


class PlannerTests(unittest.TestCase):
    def config(self, provider="anthropic", **overrides):
        return planner.load_config({
            "AI_UI_PLANNER_PROVIDER": provider,
            "AI_UI_PLANNER_MODEL": "claude-sonnet-4-6" if provider == "anthropic" else "test-model",
            "AI_UI_PLANNER_API_KEY": "private-fixture-key",
            **overrides,
        })

    def test_existing_openai_defaults_and_legacy_model_alias(self):
        config = planner.load_config({"OPENAI_API_KEY": "fixture"})
        self.assertEqual((config.provider, config.model, config.effort), ("openai", "gpt-5-mini", ""))
        config = planner.load_config({"OPENAI_API_KEY": "fixture", "AI_UI_OPENAI_MODEL": "legacy-model"})
        self.assertEqual(config.model, "legacy-model")
        config = planner.load_config({"OPENAI_API_KEY": "fixture", "AI_UI_OPENAI_MODEL": "legacy", "AI_UI_PLANNER_MODEL": "explicit"})
        self.assertEqual(config.model, "explicit")

    def test_anthropic_uses_its_own_key_and_explicit_model(self):
        config = planner.load_config({
            "AI_UI_PLANNER_PROVIDER": "anthropic", "AI_UI_PLANNER_MODEL": "claude-sonnet-4-6",
            "ANTHROPIC_API_KEY": "claude-fixture", "OPENAI_API_KEY": "other-fixture",
        })
        self.assertEqual(config.api_key, "claude-fixture")
        self.assertNotIn("claude-fixture", repr(config))
        with self.assertRaisesRegex(planner.PlannerError, "AI_UI_PLANNER_MODEL"):
            planner.load_config({"AI_UI_PLANNER_PROVIDER": "anthropic", "AI_UI_OPENAI_MODEL": "ignored"})
        with self.assertRaisesRegex(planner.PlannerError, "ANTHROPIC_API_KEY"):
            planner.load_config({"AI_UI_PLANNER_PROVIDER": "anthropic", "AI_UI_PLANNER_MODEL": "claude-sonnet-4-6", "OPENAI_API_KEY": "ignored"})

    def test_provider_and_effort_validation(self):
        for effort in ("low", "medium", "high", "xhigh", "max"):
            self.assertEqual(self.config(AI_UI_PLANNER_EFFORT=effort).effort, effort)
        for effort in ("none", "minimal", "ultra", "typo"):
            with self.subTest(effort=effort), self.assertRaisesRegex(planner.PlannerError, "Unsupported effort"):
                self.config(AI_UI_PLANNER_EFFORT=effort)
        with self.assertRaisesRegex(planner.PlannerError, "Unknown planner provider"):
            self.config(provider="typo")
        for model in ("", "bad\nmodel", "bad model"):
            with self.assertRaisesRegex(planner.PlannerError, "valid model ID"):
                self.config(AI_UI_PLANNER_MODEL=model)

    def test_anthropic_request_has_effort_schema_and_images(self):
        config = self.config(AI_UI_PLANNER_EFFORT="high", AI_UI_PLANNER_MAX_OUTPUT_TOKENS="32768")
        request = planner.build_request(config, "System instructions", CONTENT, contract.PLANNER_SCHEMA)
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(request.get_header("X-api-key"), "private-fixture-key")
        self.assertEqual(request.get_header("Anthropic-version"), "2023-06-01")
        self.assertIsNone(request.get_header("Authorization"))
        self.assertEqual(payload["model"], "claude-sonnet-4-6")
        self.assertEqual(payload["max_tokens"], 32768)
        self.assertEqual(payload["output_config"]["effort"], "high")
        self.assertEqual(payload["system"], "System instructions")
        self.assertEqual(payload["messages"][0]["content"][0], {"type": "text", "text": "Verify settings"})
        self.assertEqual(payload["messages"][0]["content"][1]["source"], {"type": "base64", "media_type": "image/png", "data": "cG5n"})
        schema = payload["output_config"]["format"]["schema"]
        self.assertEqual(payload["output_config"]["format"]["type"], "json_schema")
        self.assertFalse(schema["additionalProperties"])
        self.assertIn("name", schema["required"])
        self.assertNotIn("minLength", schema["properties"]["name"])
        self.assertIn("minLength", contract.PLANNER_SCHEMA["properties"]["name"])

    def test_default_effort_is_omitted_and_explicit_effort_is_forwarded(self):
        for provider in ("openai", "anthropic", "openai-compatible"):
            for effort in ("", "default", "high"):
                with self.subTest(provider=provider, effort=effort):
                    config = self.config(provider, AI_UI_PLANNER_EFFORT=effort,
                                         AI_UI_PLANNER_BASE_URL="https://endpoint.example/v1" if provider == "openai-compatible" else "")
                    payload = json.loads(planner.build_request(config, "System", CONTENT, contract.PLANNER_SCHEMA).data)
                    actual = payload.get("reasoning", {}).get("effort") if provider == "openai" else payload.get("output_config", {}).get("effort") if provider == "anthropic" else payload.get("reasoning_effort")
                    self.assertEqual(actual, "high" if effort == "high" else None)

    def test_anthropic_reads_text_and_excludes_thinking(self):
        payload = {"stop_reason": "end_turn", "content": [
            {"type": "thinking", "thinking": "Private reasoning"},
            {"type": "text", "text": json.dumps(SCENARIO)},
        ]}
        self.assertEqual(planner.decode_response("anthropic", payload), SCENARIO)

    def test_anthropic_refusal_and_token_limit_are_rejected_even_with_valid_json(self):
        for reason in ("refusal", "max_tokens", "tool_use", "pause_turn", None):
            with self.subTest(reason=reason), self.assertRaisesRegex(planner.PlannerError, "end_turn"):
                planner.decode_response("anthropic", {"stop_reason": reason, "content": [{"type": "text", "text": json.dumps(SCENARIO)}]})

    def test_openai_response_and_incomplete_or_refused_response(self):
        payload = {"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(SCENARIO)}]}]}
        self.assertEqual(planner.decode_response("openai", payload), SCENARIO)
        with self.assertRaisesRegex(planner.PlannerError, "did not complete"):
            planner.decode_response("openai", {**payload, "status": "incomplete"})
        with self.assertRaisesRegex(planner.PlannerError, "refused"):
            planner.decode_response("openai", {"output": [{"type": "message", "content": [{"type": "refusal"}]}]})

    def test_missing_or_invalid_json_does_not_become_a_scenario(self):
        for value in ("", "not JSON", "[]", "```json\n{}\n```"):
            with self.subTest(value=value), self.assertRaises(planner.PlannerError):
                planner.decode_response("anthropic", {"stop_reason": "end_turn", "content": [{"type": "text", "text": value}]})

    def test_portable_wire_schema_keeps_runtime_validation(self):
        config = self.config()
        planner.build_request(config, "System", CONTENT, contract.PLANNER_SCHEMA)
        for invalid in ({"name": " ", "steps": [{"action": "wait", "seconds": 0}]},
                        {"name": "Bad", "unknown": True, "steps": [{"action": "wait", "seconds": 0}]},
                        {"name": "Bad", "steps": [{"action": "wait", "seconds": 0, "unknown": True}]},
                        {"name": "Bad", "steps": [{"action": "wait", "seconds": -1}]},
                        {"name": "Bad", "steps": [{"action": "tap", "id": "button", "timeout": 0}]}):
            with self.assertRaises(contract.ScenarioContractError):
                contract.normalize_planner_scenario(invalid)

    def test_remote_errors_do_not_echo_private_body_or_retry(self):
        config = self.config(AI_UI_PLANNER_EFFORT="xhigh")
        opener = mock.Mock()
        opener.open.side_effect = urllib.error.HTTPError("https://api.anthropic.com", 400, "private-fixture-key", {}, None)
        with mock.patch.object(planner.urllib.request, "build_opener", return_value=opener):
            with self.assertRaises(planner.PlannerError) as caught:
                planner.generate_scenario(config, "Private context", CONTENT, contract.PLANNER_SCHEMA)
        self.assertIn("HTTP 400", str(caught.exception))
        self.assertIn("effort=xhigh", str(caught.exception))
        self.assertNotIn("private-fixture-key", str(caught.exception))
        opener.open.assert_called_once()

    def test_invalid_endpoints_and_budgets_fail_before_network(self):
        for url in ("", "http://example.com/v1", "https://key@example.com/v1", "https://example.com/v1?api_key=secret", "https://example.com/#fragment", "https://example.com:bad/v1", "https://[invalid/v1", "https://example.com/a path"):
            with self.subTest(url=url), self.assertRaisesRegex(planner.PlannerError, "AI_UI_PLANNER_BASE_URL"):
                self.config("openai-compatible", AI_UI_PLANNER_BASE_URL=url)
        with self.assertRaisesRegex(planner.PlannerError, "only to openai-compatible"):
            self.config(AI_UI_PLANNER_BASE_URL="https://other.example/v1")
        for value in ("0", "-1", "bad"):
            with self.assertRaisesRegex(planner.PlannerError, "positive integer"):
                self.config(AI_UI_PLANNER_MAX_OUTPUT_TOKENS=value)
        with self.assertRaisesRegex(planner.PlannerError, "single line"):
            self.config(AI_UI_PLANNER_API_KEY="private\ncredential")


class LocalEndpointTests(unittest.TestCase):
    def test_compatible_endpoint_roundtrip_and_redirect_protection(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                requests.append((self.path, dict(self.headers), json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                if self.path.startswith("/redirect/"):
                    self.send_response(302)
                    self.send_header("Location", "/credential-leak")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(SCENARIO)}}]}).encode())

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = {"AI_UI_PLANNER_PROVIDER": "openai-compatible", "AI_UI_PLANNER_MODEL": "local-vision-model", "AI_UI_PLANNER_EFFORT": "high",
                   "AI_UI_PLANNER_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1"}
            self.assertEqual(planner.generate_scenario(planner.load_config(env), "System", CONTENT, contract.PLANNER_SCHEMA), SCENARIO)
            self.assertEqual(requests[0][0], "/v1/chat/completions")
            self.assertNotIn("Authorization", requests[0][1])
            self.assertEqual(requests[0][2]["model"], "local-vision-model")
            self.assertEqual(requests[0][2]["reasoning_effort"], "high")
            self.assertEqual(requests[0][2]["messages"][1]["content"][1]["image_url"]["url"], CONTENT[1]["image_url"])
            redirect_config = planner.load_config({**env, "AI_UI_PLANNER_API_KEY": "fixture-secret", "AI_UI_PLANNER_BASE_URL": f"http://127.0.0.1:{server.server_port}/redirect"})
            with self.assertRaisesRegex(planner.PlannerError, "HTTP 302"):
                planner.generate_scenario(redirect_config, "System", CONTENT, contract.PLANNER_SCHEMA)
            self.assertEqual([r[0] for r in requests], ["/v1/chat/completions", "/redirect/chat/completions"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
