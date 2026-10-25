# Remote card explanations

Answer generation is optional. Select **Include a cited explanation** to generate from the exact selected evidence in the retrieval trace. Every citation links to that card's complete text. An absent, failed, or unverified provider leaves retrieval available. Empty evidence produces an explicit insufficient-evidence response without a remote call.

The browser now uses [streamed saved-turn answers and Stop](streaming.md). The synchronous search option described below remains available to API clients.

Answers receive the original user question, actual retrieval query, and a frozen conversational-context snapshot separately from selected card evidence. The snapshot contains at most six earlier turns from that conversation, completed answers only, a 16,000-character history budget, and a 4,000-character limit per older text field. Any clipping or omitted older context is recorded as `answer_context.context_truncated`; the original submitted question, actual query, and card evidence remain complete. Failed/cancelled partial answers and turns added after retrieval are excluded. Both synchronous and streamed generation use the same saved snapshot.

## Provider prerequisite

Checked 2026-10-25: [OpenCode Go's workload guidance](https://opencode.ai/v2/docs/console/go/#where-can-i-use-it) requests typical coding-agent traffic. Magic card Q&A suitability is unresolved. The [inference API](https://opencode.ai/v2/docs/console/api/inference/) documents compatible HTTP interfaces, but this does not establish workload suitability. No Go generation request was sent, no paid alternative was selected, and no live-provider smoke test was run. Confirm suitability with the provider before enabling requests.

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

There is no default endpoint, model, or paid service. The adapter implements Chat Completions JSON responses; other API families need another adapter. The endpoint must support JSON-object response format. HTTP loopback is allowed for local test providers; other endpoints require HTTPS. Credentials are sent in the Authorization header and never included in the browser status, traces, or exception messages. Environment variables are read at service startup; `.env` files are not loaded automatically.

The UI's provider status comes from `GET /api/provider`. `POST /api/search` accepts `generate_answer: true` and uses whichever retrieval mode selected the evidence. `trace.generation` includes `status`, a safe message, and, on success, `text`, `insufficient_evidence`, and validated `{card_id,name}` citations. Unknown card citations, malformed answer payloads, and uncited supported answers fail explicitly while preserving evidence. Card text cannot establish every rules interaction; the prompt and UI state that explanations are not authoritative rulings. Validation establishes citation identity, not truth of generated claims; real-model review is still required.

## Validation

`uv run pytest backend/tests/test_generation.py` exercises the FastAPI seam with isolated real SQLite and deterministic provider substitutes, including the actual HTTP adapter with a substituted external transport. Browser tests cover unavailable-provider evidence retention and citation navigation. These tests do not establish remote model quality or live Go support.

When workload approval and credentials are available, run a separate smoke check using a known card query, inspect the answer's citations and insufficient-evidence behavior, and record model, date, and outcome without the key. Until then, the live integration remains unverified.
