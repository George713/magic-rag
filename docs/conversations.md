# Saved conversations

The first browser search creates a local conversation automatically. **New conversation** creates a fresh chat. Use a conversation title to reopen its most recent turn, then select an earlier question to inspect its original evidence. Delete removes that conversation and all its turns. These changes survive service and browser restarts.

Conversations share the configured `MAGIC_RAG_DB` SQLite database with card retrieval. Historical turns contain complete retrieval trace snapshots, including original question, actual query, filters, candidates, selected readable evidence, corpus/model configuration, stage timings, and provider/rewrite status. Reopening never searches the current corpus. Refreshing or replacing the corpus therefore does not rewrite old evidence.

Retrieval works without a remote provider. A saved turn has state `retrieval_complete` when generation is unconfigured. The turn contract also reserves `completed`, `failed`, and `cancelled` states for answer generation, with separate nullable `answer` and `error` fields; the trace retains the original generation contract.

## API

- `POST /api/conversations` creates a conversation and returns its detail with status 201.
- `GET /api/conversations` lists summaries, most recently updated first.
- `GET /api/conversations/{id}` returns the conversation and ordered turns.
- `DELETE /api/conversations/{id}` deletes its history and returns status 204.
- `POST /api/search` accepts optional `conversation_id`. The response adds `conversation_id` and `turn_id` and saves that exact trace. Omitting the ID leaves standalone retrieval available without saving a turn. Unknown/deleted IDs return 404, and invalid searches do not create turns.

Conversation titles initially read “New conversation” and use the first submitted question (up to 80 characters) after a successful retrieval. No title or trace contains provider credentials.

## Verification

```powershell
uv run pytest backend/tests/test_conversations.py
cd web
npx playwright test -c playwright.conversations.config.ts
```

The API tests use a temporary real SQLite database across application instances and check immutable evidence after source data changes, deletion, and isolation. The browser check exercises two turns, selecting earlier evidence, fresh chat, page reload, reopen, and delete through SvelteKit and FastAPI on ports 8107/5207. It uses an isolated ignored `test-results/conversations.db`.
