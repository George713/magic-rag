# Remote card explanations

Sending a message retrieves cards and requests a streamed answer from the exact selected evidence. Validated citations remain in the answer data; the interface exposes supporting card text through that turn's Retrieved evidence disclosure instead of a Sources line. An absent, failed, or unverified provider leaves retrieval available. Empty evidence produces an explicit insufficient-evidence response without a remote call.

The browser now uses [streamed saved-turn answers and Stop](streaming.md). The synchronous search option described below remains available to API clients.

Answers receive the original user question, actual retrieval query, and a frozen conversational-context snapshot separately from selected card evidence. The snapshot contains at most six earlier turns from that conversation, completed answers only, a 16,000-character history budget, and a 4,000-character limit per older text field. Any clipping or omitted older context is recorded as `answer_context.context_truncated`; the original submitted question, actual query, and card evidence remain complete. Failed/cancelled partial answers and turns added after retrieval are excluded. Both synchronous and streamed generation use the same saved snapshot.

## Provider prerequisite

Checked 2026-10-25: [OpenCode Go's workload guidance](https://opencode.ai/v2/docs/console/go/#where-can-i-use-it) requests typical coding-agent traffic. The [inference API](https://opencode.ai/v2/docs/console/api/inference/) documents compatible HTTP interfaces, but this does not establish workload suitability. The maintainer set `MAGIC_RAG_PROVIDER_SUITABILITY_CONFIRMED` locally; that flag records the maintainer's decision and is not provider approval.

### Live tool-calling smoke test

`scripts/smoke_provider_tool_calls.py` is a manual check outside the automated suite. It reads the `MAGIC_RAG_PROVIDER_*` variables from the repository `.env` (process environment overrides; `--env-file` selects another file). It refuses to run, exit code 2, unless the suitability flag is `true`. It then sends one tool-calling request through LangChain's `ChatOpenAI` with a single `search_cards(query: str)` tool, repeats it as a streamed request, and reports whether each returns a well-formed `search_cards` call with a non-empty `query` string and a call ID. Credentials are never printed. The application's full chat-completions URL is converted to the API base LangChain expects by removing the `/chat/completions` suffix.

```powershell
uv run python scripts/smoke_provider_tool_calls.py            # add --no-stream to skip the streamed check
```

Recorded run, 2026-11-14, model `glm-5.3-flash` on OpenCode Go:

- **Outcome: tool calls work.** On two consecutive runs, both the non-streamed and streamed requests returned exactly one `search_cards` call with `finish_reason='tool_calls'`, a call ID, and a model-written query (for example `{"query": "red instant deal 3 damage to creature"}`) for the question "a red instant that deals 3 damage to a creature".
- **Streaming:** Streamed tool-call chunks (6–7 per response) merged into a complete, parseable call with no `invalid_tool_calls`.
- **Quirk: session header required.** Requests without an `x-opencode-session` header fail with HTTP 400 ("Request is missing x-opencode-session and cannot be routed efficiently"). Go's client guidance asks clients to send a stable session ID per conversation and an application-specific user agent. The script sends a fresh UUID per run and `User-Agent: magic-rag/0.1`. The application sends the same headers, with the conversation ID as the session ID.
- The model chose to call the tool without `tool_choice` forcing. Answer quality and citation behavior were not tested.

### Live application check

Recorded run, 2026-11-14, model `glm-5.3-flash` on OpenCode Go, through the FastAPI application (in-process, a copy of the full local corpus, keyword mode, credentials from `.env`):

- **Outcome: cited answers work through LangChain's chat model.** The synchronous answer to "What does Lightning Bolt do?" completed with validated citations (Lightning Bolt and the Lightning Bolt face of Emeritus of Conflict) and accurate card text.
- **Rewriting:** the follow-up "Which of those costs less than 2 mana?" was rewritten to "Does Lightning Bolt cost less than 2 mana?".
- **Streaming:** the follow-up's streamed answer arrived in 80 text deltas and completed with four validated citations, using the JSON-object response format through LangChain's streamed path.
- Prose correctness was checked by eye on this one exchange only; it is not an evaluation of answer quality.

## Server configuration

Set these variables in the PowerShell session running **Python**, then restart that service:

```powershell
$env:MAGIC_RAG_PROVIDER_URL = '<full HTTPS chat-completions endpoint>'
$env:MAGIC_RAG_PROVIDER_MODEL = '<compatible model identifier>'
$env:MAGIC_RAG_PROVIDER_API_KEY = '<server-side API key>'
# Set only after the provider confirms this workload is suitable:
$env:MAGIC_RAG_PROVIDER_SUITABILITY_CONFIRMED = 'true'
uv run python -m magic_rag serve
```

There is no default endpoint, model, or paid service. Answer generation (synchronous and streamed) and follow-up rewriting run through LangChain's OpenAI-compatible chat model (`ChatOpenAI`), built in `magic_rag.providers` from these variables. The configured value is the full chat-completions URL; the `/chat/completions` suffix is removed to form LangChain's API base. Every request sends `User-Agent: magic-rag/0.1`, the conversation ID as `x-opencode-session`, and the JSON-object response format, which the endpoint must support. Requests time out after 60 seconds and are not retried. HTTP loopback is allowed for local test providers; other endpoints require HTTPS. Credentials are sent in the Authorization header and never included in the browser status, traces, or exception messages. Environment variables are read at service startup; `.env` files are not loaded automatically.

The UI's provider status comes from `GET /api/provider`. `POST /api/search` accepts `generate_answer: true` and uses whichever retrieval mode selected the evidence. `trace.generation` includes `status`, a safe message, and, on success, `text`, `insufficient_evidence`, and validated `{card_id,name}` citations. Unknown card citations, malformed answer payloads, and uncited supported answers fail explicitly while preserving evidence. Card text cannot establish every rules interaction; the prompt and UI state that explanations are not authoritative rulings. Validation establishes citation identity, not truth of generated claims; real-model review is still required.

## Validation

The answer JSON contract accepts optional `text`, `citations`, `insufficient_evidence`, and `assets` (a list of selected-evidence card IDs). Text-only, assets-only, and combined responses are supported. Usable text or at least one selected asset is required; supported prose still requires citations. Unknown fields, invented IDs, and model-supplied image URLs fail validation. The service resolves assets to the turn's saved card metadata only after successful completion; partial or cancelled streams do not publish validated assets. Source metadata may be absent on older saved turns, which remain readable. Validation does not establish the truth of prose or the availability of external images.

`uv run pytest backend/tests/test_generation.py` exercises the FastAPI seam with isolated real SQLite. The chat model is the single substitution point: tests pass `create_app(chat_model=...)` a deterministic scripted LangChain chat model (`backend/tests/scripted_chat_model.py`) that returns predetermined answers, streamed fragments, failures, or tool calls, and records each request. No routine check makes a remote call. Browser tests cover unavailable-provider evidence retention and access through the evidence disclosure. These tests do not establish remote model quality.

Live checks run separately from the automated suite (see the recorded runs above). Record model, date, and outcome without the key.
