# Streaming and stopping answers

Select **Include a cited explanation** and submit a question. Retrieval is saved first; its complete evidence stays visible while the answer streams. **Stop answer** ends generation promptly and retains the partial text with an explicit cancelled state. Partial or failed output has no validated citations and is never labelled completed. Reopening a conversation shows the saved state and original evidence.

The application supports one Python process per database. At startup, any `generating` turn left by an interrupted process becomes `cancelled`; committed partial text remains available. Remote cancellation is best effort and cannot guarantee the provider stops billing immediately.

## Service contract

1. `POST /api/search` with a `conversation_id` saves the retrieved turn and returns `turn_id`. The UI uses `generate_answer: false` so retrieval is available before any remote answer starts. The synchronous option remains available for API clients.
2. `POST /api/conversations/{conversation_id}/turns/{turn_id}/stream` starts an answer using that saved turn's exact question and selected evidence. The response is `application/x-ndjson`, one JSON event per line:

   ```json
   {"event":"start","generation":{"status":"generating","message":"Generating from selected evidence.","text":"","citations":[]}}
   {"event":"delta","text":"An incremental text fragment"}
   {"event":"done","generation":{"status":"completed","message":"Answer grounded in selected card evidence.","text":"An incremental text fragment","citations":[{"card_id":"retrieved-id","name":"Retrieved card"}],"insufficient_evidence":false}}
   ```

3. `POST /api/conversations/{conversation_id}/turns/{turn_id}/cancel` persists cancellation, wakes a waiting stream, and cancels its upstream task. The returned generation state is authoritative; already completed turns remain completed. Browser disconnection also closes the provider stream and saves cancellation. A terminal turn cannot restart generation; submit a new question instead.

Each delta is committed to the turn. Compare-and-set updates prevent late chunks or completion from overwriting cancelled/failed/completed states. Provider errors, malformed citations, truncated streams, and streams without final validation produce `failed` with safe messages and partial text. Credentials and remote exception details are never emitted.

SvelteKit forwards the response body without buffering and propagates disconnection. The browser decodes newline-delimited events across arbitrary network chunk boundaries. It ignores late updates after Stop and keeps retrieved evidence available if the connection fails.

## Remote adapter

The compatible adapter sends `stream: true` and reads provider SSE content deltas. It incrementally decodes the JSON answer's `text` field, including split escape sequences, while withholding citations until the final payload validates. It requires a successful `stop` finish reason and `[DONE]`; EOF, token-limit termination, invalid JSON, unknown citations, and supported answers without citations fail explicitly. Text remains provisional until final validation. See [provider prerequisites](providers.md); live OpenCode Go suitability and credentials remain unresolved, so no live-provider smoke was run.

## Verification

```powershell
uv run pytest backend/tests/test_streaming.py
cd web
npm test -- --config playwright.streaming.config.ts
```

API checks use real isolated SQLite with deterministic async provider/HTTP transports. They verify incremental events, persistence after restart, cancellation, disconnection, invalid citations, EOF failures, and restart recovery. Browser checks run the actual FastAPI and SvelteKit processes with a controlled provider and verify incremental display before completion, Stop, reopening completed/cancelled turns, and recovery after failure.
