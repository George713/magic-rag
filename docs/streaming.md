# Streaming and stopping answers

Send a message to retrieve evidence and automatically stream an answer. Retrieval is saved first; its complete evidence stays visible while the answer streams. **Stop** ends generation promptly and retains the partial text with an explicit cancelled state. Partial or failed output has no validated citations or assets and is never labelled completed. Reopening a conversation shows the saved state and original evidence. **Copy answer** copies displayed generated text; assets-only answers do not invent text for copying.

The application supports one Python process per database. At startup, any `generating` turn left by an interrupted process becomes `cancelled`; committed partial text remains available. Stop aborts the active stream immediately and independently sends a cancellation request with a three-second timeout; a stalled cancellation endpoint cannot keep the provider stream open or overwrite a subsequent turn's status. Remote cancellation is best effort and cannot guarantee the provider stops billing immediately.

## Service contract

1. `POST /api/search` with a `conversation_id` saves the retrieved turn and returns `turn_id`. The UI uses `generate_answer: false` so retrieval is available before any remote answer starts. The synchronous option remains available for API clients.
2. `POST /api/conversations/{conversation_id}/turns/{turn_id}/stream` starts an answer using that saved turn's exact question, actual retrieval query, frozen bounded conversational context, and selected evidence. The response is `application/x-ndjson`, one JSON event per line:

   ```json
   {"event":"start","generation":{"status":"generating","message":"Generating from selected evidence.","text":"","citations":[]}}
   {"event":"delta","text":"An incremental text fragment"}
   {"event":"done","generation":{"status":"completed","message":"Answer grounded in selected card evidence.","text":"An incremental text fragment","citations":[{"card_id":"retrieved-id","name":"Retrieved card"}],"insufficient_evidence":false}}
   ```

3. `POST /api/conversations/{conversation_id}/turns/{turn_id}/cancel` persists cancellation, wakes a waiting stream, and cancels its upstream task. The returned generation state is authoritative; already completed turns remain completed. Browser disconnection also closes the provider stream and saves cancellation. A terminal turn cannot restart generation; submit a new question instead.

Each delta is committed to the turn. Compare-and-set updates prevent late chunks or completion from overwriting cancelled/failed/completed states. Provider errors, malformed citations, truncated streams, and streams without final validation produce `failed` with safe messages and partial text. Credentials and remote exception details are never emitted.

SvelteKit forwards the response body without buffering and propagates disconnection. The browser decodes newline-delimited events across arbitrary network chunk boundaries. It ignores late updates after Stop and keeps retrieved evidence available if the connection fails.

## Remote model

The answer streams from LangChain's OpenAI-compatible chat model. The provider accumulates content chunks and incrementally decodes the JSON answer's `text` field, including split escape sequences, while withholding citations until the final payload validates. It requires a `stop` finish reason; a stream that ends early, token-limit termination, invalid JSON, unknown citations, and supported answers without citations fail explicitly. Text remains provisional until final validation. Stop and disconnection close the model stream. See [provider configuration and live checks](providers.md).

## Verification

```powershell
uv run pytest backend/tests/test_streaming.py
cd web
npm test -- --config playwright.streaming.config.ts
```

API checks use real isolated SQLite with a deterministic scripted chat model. They verify incremental events, persistence after restart, cancellation, disconnection, invalid citations, EOF failures, and restart recovery. Browser checks run the actual FastAPI and SvelteKit processes with the scripted chat model and verify incremental display before completion, Stop, reopening completed/cancelled turns, and recovery after failure.
