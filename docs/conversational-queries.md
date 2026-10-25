# Conversational search queries

With a configured, workload-approved provider, follow-up searches make a separate remote call to produce a standalone retrieval query. The original question remains the chat question and the answer-generation input. Keyword search, query embeddings, and cross-encoder reranking all receive the actual standalone query shown in the inspector.

Rewriting uses the last six turns of the current conversation: original questions, previous actual queries, and completed answers when present. Completed selected card assets contribute bounded names and identities, so follow-ups can refer to cards shown without prose. Failed/cancelled partial answers and selections are omitted. This is conversational context, not verified card evidence. Retrieved card texts are supplied separately to answer generation; they are not copied into the rewrite request. Conversations never share history with one another.

Answer generation also receives the actual query and a bounded frozen copy of earlier conversational context, separately from the selected card evidence. That snapshot is saved with retrieval and reused for both synchronous and streamed answers, so future turns cannot change an earlier answer's context. See [answer-context limits](providers.md).

The first turn has no earlier context and is searched as submitted. When rewriting is available its status is `not_needed`. A successful follow-up records `rewritten`. If the provider is absent, its suitability is unconfirmed, its request fails, or its response is malformed, the status is `unavailable` and the submitted text is searched **exactly as-is** under the current explicit filters. The interface explains the fallback and recommends a self-contained question. It never claims an unavailable rewrite resolved a contextual reference.

The inspector and saved trace retain `question`, actual `query`, `rewrite.status`, `rewrite.message`, and measured `rewrite.elapsed_ms` (also in `timings_ms.rewrite`). The retrieval total includes rewriting; individual keyword/vector/fusion/reranking timings remain separate. Reopening a turn displays its original saved provenance without rewriting or searching again.

## Explicit filters

Rewriting can only return a `query` string. Extra response fields, including proposed filters, invalidate the rewrite and trigger the transparent fallback. Explicit color/type/mana constraints remain independent of the provider.

The browser resubmits its active controls on every search. API clients may omit `filters` to use the conversation's persisted current controls; supplying `{}` explicitly clears them. A new conversation with omitted filters starts unconstrained. Historical turn snapshots do not determine current controls. See [exact filter semantics](filters.md).

## Provider and verification

The existing server-side provider/model/key configuration and workload-suitability guard also govern rewriting. `ChatCompletionsProvider.rewrite` uses a separate async JSON request with the stable conversation session ID and a 30-second HTTP timeout. No default paid provider is selected. OpenCode Go's suitability for this card-assistance workload remains unresolved; no live rewrite or answer request has been sent under that assumption.

```powershell
uv run pytest backend/tests/test_rewriting.py
cd web
npx playwright test -c playwright.rewriting.config.ts
```

Deterministic API tests cover the artifact-sacrifice topic followed by “Any cheaper ones?” across all four retrieval modes, unchanged explicit filters, filter inheritance/clear, conversation isolation, saved provenance, malformed/outage fallback, completed-vs-partial history, and the production adapter using an external HTTP transport substitute. The browser check on isolated ports 8111/5211 covers original/actual query display, retained controls, fallback, subsequent standalone search, reopening history, and mobile layout. These checks establish behavior, not remote-model rewrite quality. A live provider smoke remains subject to suitability and credentials.
