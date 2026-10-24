# Model providers

The AI step proposes **one check** from a decision. It is optional: manual and recorded proposals need no model. A developer still calibrates and approves every check, so the provider cannot weaken the gate. A weak, wrong or hostile model can only produce a draft that fails local validation.

Pick a provider with `DDG_PROVIDER` or `ddg propose --provider NAME`. Without either, DDG uses the API key you set: `GEMINI_API_KEY` selects `gemini_api`; otherwise `ANTHROPIC_API_KEY` selects `anthropic_api`. Pick the model with `DDG_MODEL` or `--model`. List the choices with `ddg providers`.

| Provider | Uses | Needs | Notes |
|---|---|---|---|
| `gemini_api` (default) | Google Gemini API | `GEMINI_API_KEY`, `DDG_GEMINI_MODEL` (or `DDG_MODEL`), `pip install ".[ai]"` | The original provider. |
| `anthropic_api` | Anthropic Messages API through the official `anthropic` SDK | `ANTHROPIC_API_KEY`, `pip install ".[anthropic]"`; model `DDG_MODEL` or `DDG_ANTHROPIC_MODEL`, default **Claude Haiku 5.5** (`claude-haiku-5-5`) | `ANTHROPIC_BASE_URL` for a gateway. No SDK retries; a refusal or a cut-off answer is a provider error, never a draft. |
| `openai_api` | Chat Completions | `OPENAI_API_KEY`, `DDG_MODEL` | Also any OpenAI-compatible server: set `OPENAI_BASE_URL` (Ollama `http://localhost:11434/v1`, vLLM, LM Studio, LiteLLM, OpenRouter, Azure gateway). A key is optional only for a custom base URL. |
| `bedrock` | Amazon Bedrock Converse | `DDG_MODEL` (model or inference-profile id), region (`DDG_AWS_REGION`, `AWS_REGION` or `AWS_DEFAULT_REGION`), and either `AWS_BEARER_TOKEN_BEDROCK` or `pip install ".[bedrock]"` with normal AWS credentials | With boto3 the usual AWS chain applies (profile, SSO, role). |
| `claude_cli` | Claude Code subscription (`claude -p`) | `claude` on PATH and logged in | Runs with tools off, no settings, a one-line system prompt. About 500 input tokens per call. |
| `codex_cli` | Codex CLI subscription (`codex exec`) | `codex` on PATH and logged in | Read-only sandbox, ephemeral session. Slow start: allow about a minute. |
| `custom_cli` | Any command | `DDG_CLI_COMMAND` as a JSON array | The prompt is sent on stdin, the answer is read from stdout. `{model}` is replaced by `DDG_MODEL`. Use it for Gemini CLI and other agents. |

Example for a CLI that is not built in:

```
DDG_PROVIDER=custom_cli
DDG_CLI_COMMAND=["gemini","-p","Answer the prompt on stdin","-m","{model}"]
```

(That command line is an example of the mechanism. It is not tested against Gemini CLI.)

## Safety rules

- **Secrets:** API keys are read from the environment or a local `.env` and are never written to drafts, reports or error messages. Errors carry a stable code (`provider_auth_failed`, `provider_rate_limited`, `provider_timeout`, `provider_unavailable`, `provider_response_invalid`, `provider_config`), not the response body.
- **Network:** HTTP providers require `https` (plain `http` only for `localhost`) and never follow redirects, so a credential cannot be sent to another host. Responses over 1 MiB are rejected.
- **CLI agents:** each runs in an empty temporary directory, so it cannot see the repository, and receives only the environment it needs to find its login (home and config directories and its own vendor variables). A timed-out process tree is killed.
- **Time limit:** 30 seconds for APIs and 180 for CLI agents. Override with `DDG_PROVIDER_TIMEOUT` (1 to 600). The value used is recorded in the draft.
- **Validation:** every provider's answer goes through the same strict schema and exact-quote citation checks, with one repair attempt. After that, the check is calibrated against known-bad, known-good and exception commits, and a developer approves it.

## Provenance

A live draft records `provider`, `model`, the client version (SDK, CLI version or API version), the timeout and the number of requests. It does not record prompts or keys. Recorded and manual drafts are labelled as such.

## Not covered

- The function adapter (`python_function_v1`) does not accept AI proposals; write its check by hand.
- Structured-output features differ between providers and are not relied on. The schema is enforced locally.
- Real-provider calls are not part of the automated tests. The tests use fake transports and fake CLI scripts. `claude_cli` and `codex_cli` were also run once by hand against a real subscription login with a trivial prompt.
