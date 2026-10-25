# Saved conversations

The first submitted message creates a local conversation automatically. **New chat** starts a fresh unrestricted chat. Use a conversation title in the left sidebar to reopen its complete ordered transcript. Each answer has expandable Retrieval details for its original query, filters, candidates, scores, and timings. The right sidebar holds controls for the next message. Delete removes that conversation and all its turns. These changes survive service and browser restarts.

Current filters are persisted independently for each chat, including edits made without sending another message. Historical turns keep immutable snapshots; opening their details never changes current controls. Source images and completed asset selections are also snapshots, so refreshing the corpus does not change historical answers. Older saved turns without imagery remain readable.

Conversations share the configured `MAGIC_RAG_DB` SQLite database with card retrieval. Historical turns contain complete retrieval trace snapshots, including original question, actual query, filters, candidates, selected readable evidence, corpus/model configuration, stage timings, and provider/rewrite status. Reopening never searches the current corpus. Refreshing or replacing the corpus therefore does not rewrite old evidence.

Retrieval works without a remote provider. A saved turn has state `retrieval_complete` when generation is unconfigured. The turn contract also reserves `completed`, `failed`, and `cancelled` states for answer generation, with separate nullable `answer` and `error` fields; the trace retains the original generation contract.

## API

- `POST /api/conversations` creates a conversation and returns its detail with status 201.
- `GET /api/conversations` lists summaries, most recently updated first.
- `GET /api/conversations/{id}` returns the conversation and ordered turns.
- `PATCH /api/conversations/{id}` accepts `{ "filters": { ... } }` and saves validated current filters independently of turns. Conversation details expose `current_filters`.
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
