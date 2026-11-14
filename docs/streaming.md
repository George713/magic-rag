# Streaming and stopping answers

Each message is one streamed request. While it runs, the message shows a live line, `searching "<query>" · N cards`, for its search, then the answer streams beneath it. The query is the follow-up rewrite, or the typed text. Its complete evidence becomes visible once the search returns. **Stop** ends the run promptly and retains any partial text with an explicit cancelled state. Partial or failed output has no validated citations or assets and is never labelled completed. Reopening a conversation shows the saved search line, the answer state, and the original evidence. **Copy answer** copies displayed generated text; assets-only answers do not invent text for copying.

A turn is `in_progress` until it becomes `completed`, `failed`, or `cancelled`. Without a ready provider, the turn completes after its search; its generation keeps the provider status. The application supports one Python process per database. At startup, any `in_progress` turn left by an interrupted process becomes `cancelled`; committed partial text remains available. Stop aborts the active request immediately and independently sends a cancellation request with a three-second timeout; a stalled cancellation endpoint cannot keep the provider stream open or overwrite a subsequent turn's status. Remote cancellation is best effort and cannot guarantee the provider stops billing immediately.

## Service contract

1. `POST /api/conversations/{conversation_id}/messages` accepts `{question, mode?, filters?, settings?}`. Omitted filters/mode inherit the conversation's current preferences; explicit ones are saved. Unknown conversations return 404 and invalid questions or modes return 422 before any turn is saved. Otherwise the turn is saved as `in_progress`, and the response is `application/x-ndjson`, one JSON event per line, in this order:

   ```json
   {"event":"start","trace":{"trace_id":"…","conversation_id":"…","turn_id":"…","question":"Delver","searches":[],"generation":{"status":"searching",…},…}}
   {"event":"search","index":0,"query":"Delver","card_count":1,"top_cards":[{"card_id":"sample-delver","name":"Delver of Secrets // Insectile Aberration"}],"search":{"query":"Delver","mode":"keyword","stages":{…},"selected_evidence":[…],"timings_ms":{…},…}}
   {"event":"delta","text":"An incremental text fragment"}
   {"event":"done","generation":{"status":"completed","message":"Answer grounded in selected card evidence.","text":"An incremental text fragment","citations":[{"card_id":"retrieved-id","name":"Retrieved card"}],"insufficient_evidence":false},"trace":{…the saved trace…}}
   ```

   `search` repeats once per completed search, with its position as `index`; `search` carries that search's retrieval details. Today's pipeline makes one search per message. Without a ready provider, or without retrieved evidence, no deltas are sent: `done` carries the provider status or the insufficient-evidence answer. `done.trace` is the saved turn trace and is authoritative.
2. `POST /api/conversations/{conversation_id}/turns/{turn_id}/cancel` persists cancellation of an `in_progress` turn, wakes a waiting run (during its search or its answer), and cancels its upstream work. The returned generation state is authoritative; already completed turns remain completed. Browser disconnection also cancels the run and saves cancellation.

`POST /api/search` remains a synchronous retrieval API for scripts and evaluation; with `conversation_id` it saves a terminal turn.

Each delta is committed to the turn. Compare-and-set updates prevent late chunks or completion from overwriting cancelled/failed/completed states. Provider errors, malformed citations, truncated streams, and streams without final validation produce `failed` with safe messages and partial text. Credentials and remote exception details are never emitted.

SvelteKit forwards the response body without buffering and propagates disconnection. The browser decodes newline-delimited events across arbitrary network chunk boundaries (`web/src/lib/message-stream.ts`), adds the turn on `start`, appends each `search`, appends deltas, and replaces the turn with the saved trace on `done`. It ignores late updates after Stop and keeps retrieved evidence available if the connection fails.

## Remote model

The answer streams from LangChain's OpenAI-compatible chat model. The provider accumulates content chunks and incrementally decodes the JSON answer's `text` field, including split escape sequences, while withholding citations until the final payload validates. It requires a `stop` finish reason; a stream that ends early, token-limit termination, invalid JSON, unknown citations, and supported answers without citations fail explicitly. Text remains provisional until final validation. Stop and disconnection close the model stream. See [provider configuration and live checks](providers.md).

## Verification

```powershell
uv run pytest backend/tests/test_streaming.py
cd web
npm test -- --config playwright.streaming.config.ts
```

API checks use real isolated SQLite with a deterministic scripted chat model. They verify event order (`start`, `search`, deltas, `done`), the no-provider path, persistence after restart, Stop during the search and during the answer, cancellation, disconnection, invalid citations, EOF failures, and restart recovery. Browser checks run the actual FastAPI and SvelteKit processes with the scripted chat model and verify the live search line before and during the answer, incremental display before completion, Stop, reopening completed/cancelled turns, and recovery after failure.
