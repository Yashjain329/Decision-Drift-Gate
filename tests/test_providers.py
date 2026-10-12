import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ddg import providers
from ddg.providers import ProviderError, cli
from ddg.providers.anthropic_api import AnthropicApi
from ddg.providers.bedrock import Bedrock
from ddg.providers.gemini_api import GeminiApi
from ddg.providers.openai_api import OpenAICompatible

SECRET = "sk-test-SECRET-123456"


class Recorder:
    def __init__(self, status=200, body=None):
        self.status, self.body, self.calls = status, body or {}, []

    def __call__(self, url, headers, body, timeout):
        self.calls.append((url, headers, body, timeout))
        return self.status, self.body


class RegistryTests(unittest.TestCase):
    def test_names_and_normalisation(self):
        self.assertEqual(set(providers.names()), {"anthropic_api", "bedrock", "claude_cli", "codex_cli",
                                                  "custom_cli", "gemini_api", "openai_api"})
        env = {"DDG_PROVIDER": "Anthropic-API", "ANTHROPIC_API_KEY": SECRET, "DDG_MODEL": "m"}
        self.assertEqual(providers.create(env=env).name, "anthropic_api")

    def test_unknown_provider_is_a_config_error(self):
        with self.assertRaises(ProviderError) as ctx:
            providers.create("nope", env={})
        self.assertEqual(ctx.exception.code, "provider_config")

    def test_timeout_bounds(self):
        p = providers.Provider()
        self.assertEqual(providers.timeout_seconds(p, {}), 30)
        self.assertEqual(providers.timeout_seconds(p, {"DDG_PROVIDER_TIMEOUT": "90"}), 90)
        for bad in ("0", "601", "abc", "-5", "1.5"):
            with self.assertRaises(ProviderError, msg=bad):
                providers.timeout_seconds(p, {"DDG_PROVIDER_TIMEOUT": bad})

    def test_clean_answer_rejects_empty_and_oversize(self):
        for bad in (None, "", "   ", 5, "x" * (providers.MAX_ANSWER_BYTES + 1)):
            with self.assertRaises(ProviderError):
                providers.clean_answer(bad)
        self.assertEqual(providers.clean_answer("{}"), "{}")


class AnthropicTests(unittest.TestCase):
    def test_request_shape_and_text_join(self):
        rec = Recorder(body={"content": [{"type": "text", "text": '{"a":'}, {"type": "tool_use"}, {"type": "text", "text": "1}"}]})
        out = AnthropicApi("claude-x", SECRET, transport=rec).complete("PROMPT", {}, 12)
        self.assertEqual(out, '{"a":1}')
        url, headers, body, timeout = rec.calls[0]
        self.assertEqual(url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(headers["x-api-key"], SECRET)
        self.assertEqual(body["messages"][0]["content"], "PROMPT")
        self.assertEqual((body["model"], timeout), ("claude-x", 12))

    def test_status_codes_map_to_stable_codes_without_leaking_the_key(self):
        for status, code in ((401, "provider_auth_failed"), (403, "provider_auth_failed"), (429, "provider_rate_limited"),
                             (500, "provider_unavailable"), (503, "provider_unavailable"), (400, "provider_rejected")):
            with self.assertRaises(ProviderError) as ctx:
                AnthropicApi("m", SECRET, transport=Recorder(status)).complete("p", {}, 1)
            self.assertEqual(ctx.exception.code, code)
            self.assertNotIn(SECRET, str(ctx.exception))

    def test_bad_responses(self):
        for body in ({}, {"content": "x"}, {"content": []}, {"content": [{"type": "text", "text": ""}]}):
            with self.assertRaises(ProviderError):
                AnthropicApi("m", SECRET, transport=Recorder(body=body)).complete("p", {}, 1)

    def test_plain_http_to_a_remote_host_is_refused(self):
        with self.assertRaises(ProviderError):
            AnthropicApi("m", SECRET, base_url="http://example.com", transport=Recorder()).complete("p", {}, 1)

    def test_factory_requires_key_and_model(self):
        with self.assertRaises(ProviderError):
            providers.create("anthropic_api", env={"DDG_MODEL": "m"})
        with self.assertRaises(ProviderError):
            providers.create("anthropic_api", env={"ANTHROPIC_API_KEY": SECRET})


class OpenAITests(unittest.TestCase):
    OK = {"choices": [{"message": {"content": '{"ok":true}'}}]}

    def test_hosted_requires_a_key_but_local_servers_do_not(self):
        with self.assertRaises(ProviderError):
            providers.create("openai_api", env={"DDG_MODEL": "m"})
        local = providers.create("openai_api", env={"DDG_MODEL": "llama3", "OPENAI_BASE_URL": "http://localhost:11434/v1"})
        rec = Recorder(body=self.OK)
        local._transport = rec
        self.assertEqual(local.complete("p", {}, 5), '{"ok":true}')
        self.assertEqual(rec.calls[0][0], "http://localhost:11434/v1/chat/completions")
        self.assertNotIn("authorization", rec.calls[0][1])

    def test_bearer_header_and_remote_http_refused(self):
        rec = Recorder(body=self.OK)
        OpenAICompatible("m", SECRET, "https://gateway.example.com/v1", transport=rec).complete("p", {}, 5)
        self.assertEqual(rec.calls[0][1]["authorization"], "Bearer " + SECRET)
        with self.assertRaises(ProviderError):
            OpenAICompatible("m", SECRET, "http://gateway.example.com/v1", transport=rec).complete("p", {}, 5)

    def test_malformed_choices(self):
        for body in ({}, {"choices": []}, {"choices": [{}]}, {"choices": [{"message": {"content": None}}]}):
            with self.assertRaises(ProviderError):
                OpenAICompatible("m", SECRET, transport=Recorder(body=body)).complete("p", {}, 1)


class BedrockTests(unittest.TestCase):
    OK = {"output": {"message": {"content": [{"text": '{"k":'}, {"text": "1}"}]}}}

    def test_bearer_token_request_quotes_the_model_id(self):
        rec = Recorder(body=self.OK)
        out = Bedrock("us.anthropic.claude-x-v1:0", "us-east-1", bearer_token=SECRET, transport=rec).complete("hi", {}, 9)
        self.assertEqual(out, '{"k":1}')
        url, headers, body, _ = rec.calls[0]
        self.assertEqual(url, "https://bedrock-runtime.us-east-1.amazonaws.com/model/us.anthropic.claude-x-v1%3A0/converse")
        self.assertEqual(headers["authorization"], "Bearer " + SECRET)
        self.assertEqual(body["messages"][0]["content"][0]["text"], "hi")

    def test_invalid_region_is_rejected_before_any_request(self):
        for region in ("us-east-1.evil.com/", "", "US-EAST-1", "x"):
            with self.assertRaises(ProviderError):
                Bedrock("m", region, bearer_token=SECRET)

    def test_boto_client_path_and_error_mapping(self):
        calls = []

        class Client:
            def converse(self, **kw):
                calls.append(kw)
                return BedrockTests.OK

        self.assertEqual(Bedrock("m", "eu-west-1", client=Client()).complete("p", {}, 5), '{"k":1}')
        self.assertEqual(calls[0]["modelId"], "m")

        class Denied(Exception):
            response = {"Error": {"Code": "AccessDeniedException", "Message": "arn:aws:iam::123456789012:user/x"}}

        class Boom:
            def converse(self, **kw):
                raise Denied("arn:aws:iam::123456789012:user/x")

        with self.assertRaises(ProviderError) as ctx:
            Bedrock("m", "eu-west-1", client=Boom()).complete("p", {}, 5)
        self.assertEqual(ctx.exception.code, "provider_auth_failed")
        self.assertNotIn("123456789012", str(ctx.exception))

    def test_factory_needs_region_and_model(self):
        with self.assertRaises(ProviderError):
            providers.create("bedrock", env={"DDG_MODEL": "m"})
        p = providers.create("bedrock", env={"DDG_MODEL": "m", "AWS_REGION": "us-west-2", "AWS_BEARER_TOKEN_BEDROCK": SECRET})
        self.assertEqual(p.client_version(), "converse-http")


class GeminiTests(unittest.TestCase):
    def test_sdk_call_shape(self):
        seen = {}

        class Interactions:
            def create(self, **kw):
                seen.update(kw)
                return SimpleNamespace(output_text='{"x":1}')

        client = SimpleNamespace(interactions=Interactions())
        self.assertEqual(GeminiApi("g", client=client).complete("P", {"type": "object"}, 20), '{"x":1}')
        self.assertEqual((seen["model"], seen["input"], seen["timeout"]), ("g", "P", 20))
        self.assertEqual(seen["response_format"]["schema"], {"type": "object"})

    def test_missing_output_text_is_invalid(self):
        client = SimpleNamespace(interactions=SimpleNamespace(create=lambda **kw: SimpleNamespace(output_text=None)))
        with self.assertRaises(ProviderError):
            GeminiApi("g", client=client).complete("P", {}, 5)

    def test_legacy_gemini_model_variable_still_works(self):
        p = providers.create("gemini_api", env={"GEMINI_API_KEY": SECRET, "DDG_GEMINI_MODEL": "gemini-x"})
        self.assertEqual(p.model, "gemini-x")


def script(body: str) -> Path:
    handle = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8")
    handle.write(textwrap.dedent(body))
    handle.close()
    return Path(handle.name)


def fake_cli(path: Path, parse=lambda out, _o: out, build=None):
    return cli.CliProvider(sys.executable, build or (lambda m, w, o: [str(path)]), parse, "model-1",
                           env=os.environ)


class CliProviderTests(unittest.TestCase):
    def tearDown(self):
        for p in getattr(self, "_files", []):
            p.unlink(missing_ok=True)

    def make(self, body, **kw):
        path = script(body)
        self._files = getattr(self, "_files", []) + [path]
        return fake_cli(path, **kw)

    def test_prompt_goes_on_stdin_and_stdout_is_the_answer(self):
        p = self.make("import sys; print(sys.stdin.read().upper())")
        self.assertEqual(p.complete("hello", {}, 30).strip(), "HELLO")

    def test_runs_in_an_empty_directory(self):
        p = self.make("import os; print(len(os.listdir('.')))")
        self.assertEqual(p.complete("x", {}, 30).strip(), "0")

    def test_only_needed_environment_reaches_the_cli(self):
        p = self.make("import os; print(os.environ.get('GEMINI_API_KEY','-'), os.environ.get('DDG_SECRET_THING','-'), "
                      "os.environ.get('GITHUB_TOKEN','-'))")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "vendor-ok", "DDG_SECRET_THING": "no", "GITHUB_TOKEN": "no"}):
            p = cli.CliProvider(sys.executable, lambda m, w, o: [str(self._files[0])], lambda out, _o: out, "m", env=os.environ)
            self.assertEqual(p.complete("x", {}, 30).split(), ["vendor-ok", "-", "-"])

    def test_timeout_kills_the_process(self):
        p = self.make("import time; time.sleep(60)")
        with self.assertRaises(ProviderError) as ctx:
            p.complete("x", {}, 2)
        self.assertEqual(ctx.exception.code, "provider_timeout")

    def test_nonzero_exit_and_empty_output_are_errors(self):
        for body, code in (("import sys; sys.exit(3)", "provider_unavailable"), ("pass", "provider_response_invalid")):
            with self.assertRaises(ProviderError) as ctx:
                self.make(body).complete("x", {}, 30)
            self.assertEqual(ctx.exception.code, code)

    def test_missing_executable_is_a_config_error(self):
        with self.assertRaises(ProviderError) as ctx:
            cli.CliProvider("definitely-not-installed-cli", lambda *a: [], lambda s, o: s)
        self.assertEqual(ctx.exception.code, "provider_config")

    def test_version_is_recorded_for_provenance(self):
        p = self.make("print('x')")
        self.assertTrue(p.client_version())
        self.assertEqual(p.describe()["model"], "model-1")


class ParserTests(unittest.TestCase):
    def test_claude_json_result(self):
        self.assertEqual(cli._claude_parse(json.dumps({"is_error": False, "result": '{"ok":1}'}), None), '{"ok":1}')

    def test_claude_error_modes(self):
        with self.assertRaises(ProviderError) as ctx:
            cli._claude_parse(json.dumps({"is_error": True, "result": "Not logged in - Please run /login"}), None)
        self.assertEqual(ctx.exception.code, "provider_auth_failed")
        with self.assertRaises(ProviderError) as ctx:
            cli._claude_parse(json.dumps({"is_error": True, "result": "overloaded"}), None)
        self.assertEqual(ctx.exception.code, "provider_unavailable")
        for bad in ("not json", "[]"):
            with self.assertRaises(ProviderError):
                cli._claude_parse(bad, None)

    def test_codex_reads_the_answer_file(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "answer.txt"
            out.write_text('{"a":1}', encoding="utf-8")
            self.assertEqual(cli._codex_parse("", out), '{"a":1}')
            with self.assertRaises(ProviderError):
                cli._codex_parse("", Path(folder) / "missing.txt")

    def test_command_lines_are_locked_down(self):
        claude = cli._claude_build("m", Path("."), Path("."))
        for flag in ("-p", "--no-session-persistence", "--strict-mcp-config", "--disable-slash-commands"):
            self.assertIn(flag, claude)
        self.assertEqual(claude[claude.index("--tools") + 1], "")
        self.assertEqual(claude[claude.index("--model") + 1], "m")
        codex = cli._codex_build(None, Path("w"), Path("o"))
        self.assertEqual(codex[codex.index("--sandbox") + 1], "read-only")
        self.assertIn("--ephemeral", codex)
        self.assertEqual(codex[-1], "-")
        self.assertNotIn("-m", codex)


class CustomCliTests(unittest.TestCase):
    def test_command_must_be_a_json_string_array(self):
        for bad in ("", "not json", "[]", '["a", 1]', '"x"'):
            with self.assertRaises(ProviderError, msg=bad):
                providers.create("custom_cli", env={"DDG_CLI_COMMAND": bad})

    def test_placeholder_and_round_trip(self):
        path = script("import sys; print(sys.argv[1], sys.stdin.read().strip())")
        try:
            env = dict(os.environ, DDG_CLI_COMMAND=json.dumps([sys.executable, str(path), "{model}"]))
            p = providers.create("custom_cli", model="mm", env=env)
            self.assertEqual(p.name, "custom_cli")
            self.assertEqual(p.complete("body", {}, 30).strip(), "mm body")
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
