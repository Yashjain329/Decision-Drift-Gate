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

    def test_all_providers_load_even_when_one_registered_first(self):
        # Regression: importing ddg.proposal registers gemini_api before names() runs.
        import subprocess
        code = "import ddg.proposal; from ddg import providers; print(len(providers.names()))"
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), "7")

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


try:  # optional extra [anthropic]; the tests drive the real SDK offline through a mock HTTP transport
    import anthropic
    import httpx2
except ImportError:
    anthropic = None


def _message(content, stop_reason="end_turn"):
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-haiku-5-5", "content": content,
            "stop_reason": stop_reason, "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}}


class AnthropicConfigTests(unittest.TestCase):
    def test_default_model_is_haiku_5_5_and_overridable(self):
        p = providers.create("anthropic_api", env={"ANTHROPIC_API_KEY": SECRET})
        self.assertEqual((p.name, p.model), ("anthropic_api", "claude-haiku-5-5"))
        self.assertEqual(providers.create("anthropic_api", env={"ANTHROPIC_API_KEY": SECRET,
                                                                "DDG_ANTHROPIC_MODEL": "claude-sonnet-5-5"}).model, "claude-sonnet-5-5")
        self.assertEqual(providers.create("anthropic_api", model="claude-opus-5-5",
                                          env={"ANTHROPIC_API_KEY": SECRET}).model, "claude-opus-5-5")
        self.assertNotIn(SECRET, json.dumps(p.describe()))

    def test_factory_requires_key(self):
        with self.assertRaises(ProviderError) as ctx:
            providers.create("anthropic_api", env={"DDG_MODEL": "m"})
        self.assertEqual(ctx.exception.code, "provider_config")

    def test_two_api_slots_pick_the_configured_key(self):
        self.assertEqual(providers.create(env={"ANTHROPIC_API_KEY": SECRET}).name, "anthropic_api")
        self.assertEqual(providers.create(env={"GEMINI_API_KEY": SECRET, "DDG_GEMINI_MODEL": "g",
                                               "ANTHROPIC_API_KEY": SECRET}).name, "gemini_api")
        self.assertEqual(providers.create(env={"DDG_PROVIDER": "anthropic_api", "GEMINI_API_KEY": SECRET,
                                               "ANTHROPIC_API_KEY": SECRET}).name, "anthropic_api")

    def test_plain_http_to_a_remote_host_is_refused(self):
        with self.assertRaises(ProviderError):
            AnthropicApi("m", SECRET, base_url="http://example.com").complete("p", {}, 1)

    def test_missing_sdk_is_a_config_error(self):
        with patch.dict(sys.modules, {"anthropic": None}):
            with self.assertRaises(ProviderError) as ctx:
                AnthropicApi("m", SECRET).complete("p", {}, 1)
        self.assertEqual(ctx.exception.code, "provider_config")


@unittest.skipUnless(anthropic, "anthropic SDK not installed (optional [anthropic] extra)")
class AnthropicSdkTests(unittest.TestCase):
    def provider(self, status=200, body=None):
        self.requests = []

        def handler(request):
            self.requests.append(request)
            return httpx2.Response(status, json=body if body is not None else {"type": "error", "error": {"type": "x", "message": SECRET}})

        client = anthropic.Anthropic(api_key=SECRET, max_retries=0,
                                     http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)))
        return AnthropicApi("claude-haiku-5-5", SECRET, client=client)

    def test_request_shape_and_text_join_skip_thinking(self):
        body = _message([{"type": "thinking", "thinking": "", "signature": "sig"},
                         {"type": "text", "text": '{"a":'}, {"type": "text", "text": "1}"}])
        self.assertEqual(self.provider(body=body).complete("PROMPT", {}, 12), '{"a":1}')
        request = self.requests[0]
        sent = json.loads(request.content)
        self.assertEqual(str(request.url), "https://api.anthropic.com/v1/messages")
        self.assertEqual(request.headers["x-api-key"], SECRET)
        self.assertEqual((sent["model"], sent["max_tokens"]), ("claude-haiku-5-5", 16000))
        self.assertEqual(sent["messages"], [{"role": "user", "content": "PROMPT"}])
        self.assertNotIn("thinking", sent)  # Haiku 5.5 runs adaptive thinking by default

    def test_status_codes_map_to_stable_codes_without_leaking_the_key(self):
        for status, code in ((401, "provider_auth_failed"), (403, "provider_auth_failed"), (429, "provider_rate_limited"),
                             (500, "provider_unavailable"), (529, "provider_unavailable"), (400, "provider_rejected")):
            with self.subTest(status=status), self.assertRaises(ProviderError) as ctx:
                self.provider(status).complete("p", {}, 1)
            self.assertEqual(ctx.exception.code, code)
            self.assertNotIn(SECRET, str(ctx.exception))

    def test_refusal_truncation_and_empty_answers_are_errors(self):
        for body in (_message([], "refusal"), _message([{"type": "text", "text": "{"}], "max_tokens"),
                     _message([]), _message([{"type": "text", "text": "  "}])):
            with self.subTest(stop=body["stop_reason"]), self.assertRaises(ProviderError):
                self.provider(body=body).complete("p", {}, 1)


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


# ---- full lifecycle with a non-Gemini live provider --------------------------------------------
class LifecycleWithProviderTests(unittest.TestCase):
    CHECK = json.loads(Path("examples/manual_check.json").read_text(encoding="utf-8"))

    def answer(self):
        return json.dumps({"status": "DRAFT", "check": self.CHECK, "reason": "fake model"})

    def lifecycle(self, provider, env=None):
        from ddg.approval import approve, validate_draft
        from ddg.demo import build_demo
        from ddg.engine import compare
        from ddg.proposal import load_context, propose
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, env or {}):
            demo = build_demo(Path(folder) / "repo")
            repo, refs = Path(demo["repo"]), demo["refs"]
            context = load_context(repo, revision=refs["decision_change"])
            draft = propose(context, "live", provider=provider)
            validation = validate_draft(repo, draft, refs)
            self.assertTrue(validation["eligible"])
            approved = approve(repo, draft, validation, "Dev", "Reviewed", commit_demo=True)
            report = compare(repo, approved["refs"]["approved_base"], approved["refs"]["regression"])
            return draft, report

    def test_fake_provider_draft_passes_calibration_approval_and_review(self):
        class Fake(providers.Provider):
            name = "bedrock"
            default_timeout = 90

            def client_version(self):
                return "boto3 9.9"

            def complete(inner, prompt, schema, timeout):
                self.assertIn("EVIDENCE_JSON", prompt)
                self.assertEqual(timeout, 90)
                return self.answer()

        draft, report = self.lifecycle(Fake("us.model-v1:0"))
        meta = draft["request_metadata"]
        self.assertEqual((meta["provider"], meta["timeout_seconds"], draft["model"], draft["sdk_version"]),
                         ("bedrock", 90, "us.model-v1:0", "boto3 9.9"))
        self.assertEqual(report["aggregate"], "FAILED")

    def test_real_subprocess_cli_provider_end_to_end(self):
        path = script("import sys, json\nsys.stdin.read()\nprint(json.dumps(%r))" % json.loads(self.answer()))
        try:
            env = {"DDG_PROVIDER": "custom_cli", "DDG_CLI_COMMAND": json.dumps([sys.executable, str(path)]),
                   "DDG_PROVIDER_TIMEOUT": "120"}
            from ddg.proposal import load_context, propose  # noqa: F401
            provider = providers.create(env={**os.environ, **env})
            draft, report = self.lifecycle(provider, env)
            self.assertEqual(draft["request_metadata"]["provider"], "custom_cli")
            self.assertEqual(draft["request_metadata"]["timeout_seconds"], 120)  # DDG_PROVIDER_TIMEOUT applied
        finally:
            path.unlink(missing_ok=True)

    def test_timeout_env_is_recorded_and_bounded(self):
        class Fake(providers.Provider):
            name = "openai_api"

            def client_version(self):
                return "chat-completions"

            def complete(inner, prompt, schema, timeout):
                self.assertEqual(timeout, 200)
                return self.answer()

        draft, _ = self.lifecycle(Fake("m"), {"DDG_PROVIDER_TIMEOUT": "200"})
        self.assertEqual(draft["request_metadata"]["timeout_seconds"], 200)

    def test_provider_failure_is_a_clean_error(self):
        from ddg.demo import build_demo
        from ddg.proposal import load_context, propose

        class Down(providers.Provider):
            name = "bedrock"

            def complete(inner, prompt, schema, timeout):
                raise ProviderError("provider_auth_failed", "Provider rejected the credentials (HTTP 403)")

        with tempfile.TemporaryDirectory() as folder:
            demo = build_demo(Path(folder) / "repo")
            context = load_context(Path(demo["repo"]), revision=demo["refs"]["decision_change"])
            with self.assertRaisesRegex(ValueError, "provider_auth_failed"):
                propose(context, "live", provider=Down("m"))

    def test_garbage_answer_gets_one_repair_then_fails(self):
        from ddg.demo import build_demo
        from ddg.proposal import load_context, propose
        calls = []

        class Bad(providers.Provider):
            name = "openai_api"

            def complete(inner, prompt, schema, timeout):
                calls.append(prompt)
                return "I cannot help with that."

        with tempfile.TemporaryDirectory() as folder:
            demo = build_demo(Path(folder) / "repo")
            context = load_context(Path(demo["repo"]), revision=demo["refs"]["decision_change"])
            with self.assertRaises(ValueError):
                propose(context, "live", provider=Bad("m"))
        self.assertEqual(len(calls), 2)
        self.assertIn("REPAIR", calls[1])
