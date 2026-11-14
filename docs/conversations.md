# Saved conversations

The first submitted message creates a local conversation automatically. **New chat** starts a fresh unrestricted chat. Use a conversation title in the left sidebar to reopen its complete ordered transcript. Each answer has expandable Retrieval details with one section per search, each showing its query, filters, candidates, scores, and timings. The right sidebar holds controls for the next message. Delete removes that conversation and all its turns. These changes survive service and browser restarts.

Current filters and search mode are persisted independently for each chat, including edits made without sending another message. New chats default to keyword search. Historical turns keep their original modes and filters; opening their details never changes current controls. Source images and completed asset selections are also snapshots, so refreshing the corpus does not change historical answers. The explicit [image repair](chat-workspace.md#search-modes-collapsed-evidence-and-legacy-images) can fill missing presentation metadata in older saved turns while preserving existing image snapshots and answer content.

Conversations share the configured `MAGIC_RAG_DB` SQLite database with card retrieval. Historical turns contain complete retrieval trace snapshots: the original question, corpus identity, provider/rewrite status, combined `selected_evidence`, and an ordered `searches` list. Each search records its actual query, its mode and filters snapshot, model configuration, effective settings, stage rankings, stage timings, and its own selected readable evidence. The current pipeline makes exactly one search per turn; the Retrieval details show one section per search. Reopening never searches the current corpus. Refreshing or replacing the corpus therefore does not rewrite old evidence.

Conversation storage is versioned in the `conversation_storage` table. Opening a database saved before ordered search lists (storage version 2) wipes its conversations and turns once; old single-query turns are never migrated or read. Card data, embeddings, and corpus identity are untouched.

Retrieval works without a remote provider. A turn is `in_progress` while its message runs, then `completed`, `failed`, or `cancelled`, with separate nullable `answer` and `error` fields. Without a ready provider a turn completes after its search and its generation keeps the provider status. See [streaming](streaming.md) for the message request.

## API

- `POST /api/conversations` creates a conversation and returns its detail with status 201.
- `GET /api/conversations` lists summaries, most recently updated first.
- `GET /api/conversations/{id}` returns the conversation and ordered turns.
- `PATCH /api/conversations/{id}` accepts `{ "filters": { ... } }`, `{ "mode": "hybrid" }`, or both, saving validated current preferences independently of turns. Modes are `keyword`, `vector`, `hybrid`, and `hybrid_rerank`. Empty updates, null preferences, and unknown fields/modes are rejected. Conversation details expose `current_filters` and `current_mode`.
- `DELETE /api/conversations/{id}` deletes its history and returns status 204.
- `POST /api/conversations/{id}/messages` sends one message as one streamed request; see [streaming](streaming.md).
- `POST /api/search` accepts optional `conversation_id`. Omitted filters/mode inherit that conversation's current preferences; explicit filters/mode are saved on successful retrieval. The response adds `conversation_id` and `turn_id` and saves that exact trace. Omitting the ID leaves standalone retrieval available without saving a turn. Unknown/deleted IDs return 404, and invalid searches do not create turns.

Conversation titles initially read “New conversation” and use the first submitted question (up to 80 characters) after a successful retrieval. No title or trace contains provider credentials.

## Verification

```powershell
uv run pytest backend/tests/test_conversations.py
cd web
npx playwright test -c playwright.conversations.config.ts
```

The API tests use a temporary real SQLite database across application instances and check immutable evidence after source data changes, deletion, and isolation. The browser check exercises two turns, selecting earlier evidence, fresh chat, page reload, reopen, and delete through SvelteKit and FastAPI on ports 8107/5207. It uses an isolated ignored `test-results/conversations.db`.
