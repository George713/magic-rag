# Conversational card workspace

Specification: [#15](https://github.com/George713/magic-rag/issues/15). Implementation: [PR #22](https://github.com/George713/magic-rag/pull/22), dependent on the original application in PR #13. Review baseline: `94254c8df10aa2990e212f59f85b418de599630d`.

The workspace uses a dark transcript between chat history and exact filters. Sending retrieves evidence and requests an answer automatically. Each turn owns its retrieval details and evidence targets. Current controls belong to the conversation; historical filter and image snapshots belong to their original turn.

Answers can contain text, selected card assets, or both. The model selects evidence card identities; the service resolves source imagery. It never accepts model-invented image URLs. Source-backed face images enlarge in a centered dialog. Legacy turns and unavailable images retain readable card evidence.

## Verification boundaries

FastAPI tests use real temporary SQLite, FTS5, and sqlite-vec with deterministic external embedding, reranking, source, and provider substitutes. Browser tests run SvelteKit and FastAPI; images and model responses are deterministic. These checks do not establish live OpenCode Go support. Workload suitability and credentials remain unresolved; no live model request or paid fallback is used.

API coverage is in `backend/tests/test_conversations.py`, `test_filters.py`, `test_corpus.py`, `test_generation.py`, `test_streaming.py`, and `test_answer_context.py`. Browser verification and acceptance assessment are recorded below after integration.

## Acceptance assessment

| Spec case | Evidence |
| --- | --- |
| 1: dark desktop workspace and narrow side panels | `workspace.spec.ts`, `search.spec.ts`; desktop/mobile screenshots inspected |
| 2: automatic ordered streaming, follow-ups, Stop and Copy | `chat.spec.ts`, `streaming.spec.ts`, `test_streaming.py`, `test_answer_context.py` |
| 3: Legendary eligibility, exact-name restriction, and clearing | `filters.spec.ts`, `test_filters.py` across all four modes |
| 4: exact color set, all card types, colorless and inclusive mana | `filters.spec.ts`, `test_filters.py` |
| 5: independent current filters, unsent edits and restarts | `workspace.spec.ts`, `test_conversations.py` using restarted services |
| 6: immutable historical filters without restoring controls | `workspace.spec.ts`, `filters.spec.ts`, `test_conversations.py` |
| 7: three answer forms and rejected invented selections/URLs | `chat.spec.ts`, `test_generation.py`, `test_streaming.py` |
| 8: separate assets, enlargement/close, both faces | `chat.spec.ts`, `test_corpus.py` |
| 9: reopened selections, source snapshots, legacy and failed images | `chat.spec.ts`, `test_corpus.py`, `test_generation.py`, `test_streaming.py` |
| 10: unavailable/failing provider and unchanged no-match filters | `generation.spec.ts`, `chat.spec.ts`, `filters.spec.ts`, `test_generation.py` |
| 11: per-turn actual query/stages/scores and distinct citation targets | `chat.spec.ts`, `workspace.spec.ts`, retrieval-mode browser suites |
| 12: delete persists, other chats remain readable | `conversations.spec.ts`, `test_conversations.py` |

## Review

Standards and specification reviews independently examined `94254c8...d268b8c` and reported zero remaining findings. Preliminary review findings were corrected: completed selected card names/identities now enter bounded follow-up context, and selected cards always have visible evidence links when imagery is absent. Integration verification also checks the image dialog's reactive binding and rapid New chat/composer interaction.

## Reproduce browser checks

From `web`, run `npx playwright test` and each configuration: `playwright.workspace.config.ts`, `playwright.chat.config.ts`, `playwright.streaming.config.ts`, `playwright.filters.config.ts`, `playwright.rewriting.config.ts`, `playwright.vector.config.ts`, `playwright.hybrid.config.ts`, and `playwright.reranking.config.ts`. Each configuration runs isolated local service processes and ignored test databases. API checks: `uv run pytest`; frontend checks: `npm run check` and `npm run build`.

## Final results

- Backend: **175 passed, 2 skipped**. The skipped tests require explicit real-model execution; deterministic integration checks passed.
- Browser: **21 passed** across standard (4), workspace (2), chat/assets (5), streaming (4), filters (2), rewriting (1), vector (1), hybrid (1), and reranking (1).
- Frontend: `npm run check` has zero errors and warnings; production build passes.
- Reviewed desktop and 390px mobile screenshots; transcript and side panels stay within the viewport.
- Required live-provider limitation remains visible: deterministic application verification does not establish OpenCode Go workload suitability or live model quality.
