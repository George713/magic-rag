# Streaming and stopping answers

Each message is one streamed request. While it runs, the message shows a live line, `searching "<query>" · N cards`, for each search the [card-search agent](conversational-queries.md) makes (up to three), then the answer streams beneath them. The query is the one the model wrote, or the typed text when no provider is ready. Each search's evidence becomes visible as soon as that search returns. When the answer is complete (or has failed), the lines fold into one collapsed "N searches" summary. It opens the Retrieval details: the turn's question, corpus, and timings, then one section per search with its query, filters, stage rankings, reranking changes, and timings. **Stop** ends the run promptly and deletes the turn: nothing from a stopped run is saved, including completed searches and partial answer text. The message leaves the transcript and its question returns to the composer, so the player can simply ask again. A provider failure partway through saves the turn as `failed` with a message to try again; its partial text has no validated citations or assets and is never labelled completed. Reopening a conversation shows the collapsed "N searches" summary, the answer state, and the original evidence. **Copy answer** copies displayed generated text; assets-only answers do not invent text for copying.

A turn is `in_progress` until it becomes `completed` or `failed`; a stopped turn is deleted instead. Without a ready provider, the turn completes after its search; its generation keeps the provider status. The application supports one Python process per database. At startup, any `in_progress` turn left by an interrupted process is deleted like a stopped one. Stop aborts the active request immediately (closing the connection already stops the run) and independently sends the Stop request with a three-second timeout; a stalled Stop endpoint cannot keep the provider stream open or touch a subsequent turn. Remote cancellation is best effort and cannot guarantee the provider stops billing immediately.

## Service contract

1. `POST /api/conversations/{conversation_id}/messages` accepts `{question, mode?, filters?, settings?}`. Omitted filters/mode inherit the conversation's current preferences; explicit ones are saved. Unknown conversations return 404 and invalid questions or modes return 422 before any turn is saved. Otherwise the turn is saved as `in_progress`, and the response is `application/x-ndjson`, one JSON event per line, in this order:

   ```json
   {"event":"start","trace":{"trace_id":"…","conversation_id":"…","turn_id":"…","question":"Delver","searches":[],"generation":{"status":"searching",…},…}}
   {"event":"search","index":0,"query":"Delver","card_count":1,"top_cards":[{"card_id":"sample-delver","name":"Delver of Secrets // Insectile Aberration"}],"search":{"query":"Delver","mode":"keyword","stages":{…},"selected_evidence":[…],"timings_ms":{…},…}}
   {"event":"delta","text":"An incremental text fragment"}
   {"event":"done","generation":{"status":"completed","message":"Answer grounded in selected card evidence.","text":"An incremental text fragment","citations":[{"card_id":"retrieved-id","name":"Retrieved card"}],"insufficient_evidence":false},"trace":{…the saved trace…}}
   ```

   `search` repeats once per completed search (at most three), in order, with its position as `index`. Its `search` field carries that search's retrieval details, and `selected_evidence` carries the combined evidence of the searches so far: deduplicated, taken by rank across searches, and capped at twice the per-search evidence limit (16 cards by default). The agent's tool calls and its reply that ends searching are not streamed. Deltas are only the answer's text. Without a ready provider, or without retrieved evidence, no deltas are sent: `done` carries the provider status or the insufficient-evidence answer. `done.trace` is the saved turn trace and is authoritative.
2. `POST /api/conversations/{conversation_id}/turns/{turn_id}/cancel` is Stop: it deletes the turn, wakes a waiting run (during its search or its answer), and cancels its upstream work. It returns 204 and is idempotent (the turn may already be gone because the connection closed first); it also deletes a turn whose run finished just before Stop arrived. If the run's stream is still open, it ends with `done` carrying a `cancelled` generation and `trace: null`. Browser disconnection also stops the run and deletes the turn. A conversation left without turns gets its default title back.

`POST /api/search` remains a synchronous retrieval API for scripts and evaluation; with `conversation_id` it saves a terminal turn.

Each delta is committed to the turn. Compare-and-set updates prevent late chunks or completion from overwriting failed/completed states or recreating a deleted turn. Provider errors, malformed citations, truncated streams, and streams without final validation produce `failed` with safe messages and partial text. Credentials and remote exception details are never emitted.

SvelteKit forwards the response body without buffering and propagates disconnection. The browser decodes newline-delimited events across arbitrary network chunk boundaries (`web/src/lib/message-stream.ts`), adds the turn on `start`, places each `search` by its index and takes its combined `selected_evidence`, appends deltas, and replaces the turn with the saved trace on `done`. On Stop it removes the turn from the transcript and ignores late updates. If the connection fails mid-run, the service deletes the turn, so the browser removes it too and shows an error.

## Remote model

The agent's search calls are ordinary requests with one bound `search_cards` tool. The answer is a separate request without tools and streams from LangChain's OpenAI-compatible chat model. The provider accumulates content chunks and incrementally decodes the JSON answer's `text` field, including split escape sequences, while withholding citations until the final payload validates. It requires a `stop` finish reason; a stream that ends early, token-limit termination, invalid JSON, unknown citations, and supported answers without citations fail explicitly. Text remains provisional until final validation. Stop and disconnection close the model stream. See [provider configuration and live checks](providers.md).

## Verification

```powershell
uv run pytest backend/tests/test_streaming.py
cd web
npm test -- --config playwright.streaming.config.ts
```

API checks use real isolated SQLite with a deterministic scripted chat model in place of the remote model. They verify event order (`start`, one `search` per search, deltas, `done`), the no-provider path, persistence after restart, Stop during the search and during the answer (the turn is deleted), disconnection, follow-ups after a stopped turn, provider failure mid-run (saved as failed, conversation still usable), invalid citations, EOF failures, and restart recovery. Browser checks run the actual FastAPI and SvelteKit processes with the scripted chat model and verify the live search lines before and during the answer, their collapse into the "N searches" summary, incremental display before completion, Stop during the search and during the answer removing the message (also after reload), the failure message, and recovery after failure.

These are deterministic checks of the application's behavior. Streaming from the real provider is covered only by the dated manual runs in [provider live checks](providers.md#live-application-check).
