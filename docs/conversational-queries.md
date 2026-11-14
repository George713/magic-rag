# Agent-written searches and follow-ups

With a configured, workload-approved provider, the card-search agent writes every search query itself, on the first message of a conversation and on follow-ups. The player's typed question stays the chat question and the answer input. Keyword search, query embeddings, and cross-encoder reranking all receive the model-written query, which appears in the live search line and in each search's Retrieval details. The graph's shape is recorded in [ADR 0005](adr/0005-hand-built-agent-graph-with-a-search-limit.md).

## How a message is searched

1. The agent's first model call receives the question and bounded conversation context, and must call `search_cards(query)`.
2. The application runs the search with the conversation's current explicit filters and search mode, and returns the selected cards with complete card text (token-budgeted windows, [ADR 0004](adr/0004-preserve-complete-card-text-through-model-windows.md)).
3. While fewer than three searches have run, the model may search again, for example with different wording or for another card being compared, or reply without a tool call to stop searching. Tool calls beyond the limit get a "search limit reached" result and never reach retrieval. A query without words counts as a search but does not run.
4. The answer is a separate request without tools. It draws on the combined evidence: the deduplicated union of every search's selected cards, taken by rank across searches (each search's first card, then each search's second, and so on) and capped at twice the per-search evidence limit, which is 16 cards with the default limit of 8. Citations and card assets must reference that combined evidence. If no search found anything, the message completes as insufficient evidence without an answer call.

A message with N searches makes N + 2 model calls below the limit: N tool calls, one reply that ends searching, and the answer. At the limit it makes 4: three tool calls and the answer.

## Conversation context

The agent receives up to six earlier turns of the current conversation: each turn's original question, its search queries, and its answer if it completed. The names and identities of card assets shown in completed turns are included too, so follow-ups such as "Any cheaper ones?" can refer to cards shown without prose. Failed turns contribute their question and queries but not their partial answer. Stopped turns are deleted, so they contribute nothing. This is conversational context, not verified card evidence: earlier card text never becomes evidence for a new message. Conversations never share history with one another.

The answer request receives this message's search queries and a frozen, bounded copy of the earlier context, separately from the card evidence. See [answer-context limits](providers.md).

## Without a provider

If the provider is absent, its suitability is unconfirmed, or its configuration is invalid, the graph takes the non-agent path. It makes one search with the typed text **exactly as-is**, under the current explicit filters and search mode, saves and shows the results, and reports the provider status instead of an answer.

## Explicit filters and search mode

The search tool takes only a query string. The model can neither see nor change the player's color, card type, mana value, and Legendary filters or the chosen search mode. The application applies them to every search. The browser resubmits its active controls with every message. API clients may omit `filters` or `mode` to use the conversation's persisted current controls; supplying `{}` explicitly clears the filters. A new conversation with omitted filters starts unconstrained. Historical turn snapshots do not determine current controls. See [exact filter semantics](filters.md).

## Provenance

Each saved turn keeps the original `question` and an ordered `searches` list. Each search records its actual `query`, its filters and mode snapshot, stage rankings, timings, and selected cards. The turn also keeps the combined `selected_evidence` and the frozen `answer_context` (`search_queries`, `conversation_context`, `context_truncated`). Reopening a turn shows its saved searches without searching again.

## Provider and verification

The server-side provider configuration and workload-suitability guard govern the agent. Every model call goes through the same LangChain chat model, with the conversation ID as the session ID. No default paid provider is selected.

```powershell
uv run pytest backend/tests/test_agent.py backend/tests/test_multisearch.py backend/tests/test_followups.py
cd web
npx playwright test -c playwright.agent.config.ts
```

**Deterministic verification.** The automated checks substitute a deterministic scripted chat model that emits predetermined tool calls and answers and records every request. API tests cover model-written queries on the first turn and on follow-ups across all four retrieval modes. They also cover ordered multi-search events, the three-search limit (a fourth call never reaches retrieval), the combined-evidence cap, unchanged filters and mode on every search, complete long card text in tool results, citations and assets checked against the combined evidence, insufficient evidence, the no-provider path, bounded follow-up context, and reopening after restart. The browser suite (isolated ports 8111/5211) covers the live search line with the model-written query, a comparison with two live lines folding into "2 searches", follow-ups under retained controls, provider failure, reopening history, and the mobile layout. These checks establish application behavior, not the quality of real model queries.

**Live provider checks.** Manual runs against OpenCode Go are recorded, with date and model, in [provider live checks](providers.md#live-application-check). They are spot checks of a few questions, not an evaluation.
