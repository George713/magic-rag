# Conversational card workspace

Specification: [#15](https://github.com/George713/magic-rag/issues/15). Implementation: [PR #22](https://github.com/George713/magic-rag/pull/22), dependent on the original application in PR #13. Review baseline: `94254c8df10aa2990e212f59f85b418de599630d`.

The workspace uses a dark transcript between chat history and exact filters. Sending retrieves evidence and requests an answer automatically. Each turn owns its retrieval details and evidence targets. Current controls belong to the conversation; historical filter and image snapshots belong to their original turn.

Answers can contain text, selected card assets, or both. The model selects evidence card identities; the service resolves source imagery. It never accepts model-invented image URLs. Source-backed face images enlarge in a centered dialog. Legacy turns and unavailable images retain readable card evidence.

## Verification boundaries

FastAPI tests use real temporary SQLite, FTS5, and sqlite-vec with deterministic external embedding, reranking, source, and provider substitutes. Browser tests run SvelteKit and FastAPI; images and model responses are deterministic. These checks do not establish live OpenCode Go support. Workload suitability and credentials remain unresolved; no live model request or paid fallback is used.

API coverage is in `backend/tests/test_conversations.py`, `test_filters.py`, `test_corpus.py`, `test_generation.py`, `test_streaming.py`, and `test_answer_context.py`. Browser verification and acceptance assessment are recorded below after integration.
