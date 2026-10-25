# Run the local application

Requires Windows, Node.js 22+, and [uv](https://docs.astral.sh/uv/getting-started/installation/). Python 3.11+ must include SQLite FTS5. The service checks FTS5 at startup and gives an actionable error if unavailable. No Docker or database server is used.

From the repository root in PowerShell:

```powershell
uv sync
uv run python -m magic_rag sample
uv run python -m magic_rag serve
```

In another terminal:

```powershell
cd web
npm ci
npm run dev
```

Open http://127.0.0.1:5173. Search `Lightning Bolt`, `Delver`, or `Flying`. The sample command installs three controlled cards, deliberately including a repeated printing and a card with two faces. This fixture is for repeatable behavior checks, not a complete or current card database. Repeating it replaces the sample atomically. It is not an importer for arbitrary external card data.

The default database is `$HOME/.magic-rag/cards.db`, outside the checkout. Set `MAGIC_RAG_DB` in the Python terminal to override it. `MAGIC_RAG_API` in the SvelteKit process optionally changes the backend URL (default `http://127.0.0.1:8000`). Bindings are local-only. Provider credentials are not needed; remote generation and conversational rewriting are visibly unavailable. Enter self-contained searches.

FTS5 uses Unicode word tokens joined with OR, treating punctuation and FTS syntax as ordinary input rather than exposing the FTS query language. BM25 scores sort ascending (more negative is better); canonical identity breaks ties. The inspector contains up to 20 candidates and selects up to 8 as evidence. Every candidate retains complete readable text and structured properties. No-match and empty-corpus states remain usable.

## Verification

```powershell
uv run pytest
cd web
npm run check
npm run build
npx playwright install chromium
npm test
```

API tests use real isolated SQLite databases at the confirmed FastAPI seam. The browser test starts both processes with an isolated database and checks submitted queries, complete two-face evidence, corpus provenance, and no matches. Browser tests reserve ports 8001 and 5173. Tests never modify the default database. Generated databases, browser reports, dependencies, credentials, and caches are ignored.

Validated on Windows with uv-managed CPython 3.14.0, SQLite FTS5, Node 22.23.2, and Chromium. Real model/provider behavior is outside this first keyword-only slice.

## Retrieval contract

For optional local model acquisition and vector-only search, see [vector-search.md](vector-search.md).
For fused keyword/vector rankings and configurable retrieval limits, see [hybrid-search.md](hybrid-search.md).
For the fourth mode and before/after cross-encoder rankings, see [reranking.md](reranking.md).
For a complete Scryfall corpus and atomic refreshes, see [corpus-import.md](corpus-import.md).

`POST /api/search` accepts `{ "question": "Delver", "mode": "keyword" }`. The response is a retrieval trace: `trace_id`, original `question`, actual `query`, `mode`, `filters`, `corpus`, `models`, effective `settings`, ranked `stages`, `selected_evidence`, `timings_ms`, `rewrite`, and `generation`. Each card has stable `card_id`, `name`, complete `text`, `mana_cost`, numeric `mana_value`, `colors`, `type_line`, `rank`, and raw `score`. Later stages can extend `stages` without changing card identity. `GET /api/health` reports SQLite version, FTS5 support, and card count.

See [saved conversations](conversations.md) for local history, reopening original evidence, deletion, and the optional search `conversation_id`.

See [exact card filters](filters.md) for color/type matching, inclusive mana-value ranges, retained controls, and candidate eligibility across retrieval modes.
