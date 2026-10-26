# Import and refresh the distinct-card corpus

Imports retain the representative source printing's HTTPS image metadata and card-page URL separately from canonical card text. Ordinary cards expose one image; double-faced cards retain named images for both faces when supplied. Retrieval cards expose `images: [{name, url}]` and `source_url`. Saved turns freeze these fields, so later corpus refreshes cannot change historical previews or selected assets. Existing databases migrate additively; older turns without image metadata stay readable. Image loading failures leave card text and retrieval details available. Click a preview to enlarge it centrally, then click anywhere, use the overlaid X, or press Escape to return. The viewer is frameless and transparent over a darkened backdrop; source artwork and printed borders are preserved.

From PowerShell in the repository root:

```powershell
uv sync --extra models --python 3.11
uv run --extra models --python 3.11 python -m magic_rag import
```

This manual command discovers the current Scryfall `oracle_cards` export, downloads it to a temporary directory outside Git, normalizes canonical card information, embeds every distinct card locally, and builds both SQLite indexes. It reports `activated`, corpus identity, distinct-card count, and elapsed time only after successful validation and activation. Failures exit nonzero with an actionable error; the previous corpus remains active. The default database is `data/cards.db` in the source checkout, independent of the terminal's working directory. Git ignores `data/` and database sidecars. `MAGIC_RAG_DB` remains available for an intentional location override.

To reuse an already downloaded **gzip JSON Lines** export:

```powershell
uv run --extra models --python 3.11 python -m magic_rag import --source C:/path/oracle-cards.jsonl.gz
```

Local files receive a SHA-256 corpus identity and source filename, without inventing an export date. Live downloads additionally record the discovered bulk ID, update timestamp, URI, and checksum. `GET /api/corpus` reports active identity and metadata; `POST /api/corpus/import` explicitly runs a live refresh through the same application service. The interface shows the corpus identity on each retrieval trace. A sample command deliberately replaces the active corpus with the small controlled sample; use a separate `MAGIC_RAG_DB` for experiments if preserving a complete import.

The application enables SQLite WAL mode and holds one read transaction across corpus identity, embedding compatibility, and all candidate branches. An in-flight search therefore retains one corpus snapshot even if a refresh activates during query embedding; later searches see the replacement. Stop the process or use SQLite's backup API when copying a database, since committed pages can reside in its WAL sidecar.

## Verified export contract

Checked against the [official bulk documentation](https://scryfall.com/docs/api/bulk-data), [live bulk metadata](https://api.scryfall.com/bulk-data), and [card schema](https://scryfall.com/docs/api/cards) on 2026-10-25:

- Discover `type=oracle_cards` from `/bulk-data`; its current fields are `jsonl_download_uri` and `compressed_size`. The export is gzip-compressed JSON Lines, one JSON card object per line. This importer does not assume a legacy JSON array or `download_uri` field.
- Send an identifying `User-Agent` and `Accept` header. Verify compressed byte size, gzip integrity, JSON parsing, canonical fields, and nonempty distinct-card count before activation. Preserve the compressed bytes even if HTTP supplies content-encoding headers.
- `oracle_id` identifies a distinct card across printings. Printing `id` is not a substitute. Duplicate printings collapse by canonical identity; conflicting normalized information for one identity fails explicitly. Records missing root identity, including unhandled reversible-card cases, stop the refresh rather than being silently discarded or assigned a printing identity.
- Canonical `name`, `type_line`, and `oracle_text` provide English information independently of the chosen printing's `lang`. Localized `printed_*` fields are not used. The verified export contains 38,997 records, including 8 Japanese printings with English canonical fields; filtering solely on `lang=en` would lose those cards.
- Retain every face's name, mana cost, type, colors, text, and power/toughness/loyalty/defense where supplied. Root numeric `cmc` supplies fractional mana value. Root colors are used when present; otherwise use the union of face colors. Color identity is a different property and is not substituted. Complete readable card documents remain stored alongside structured filter properties.

The live downloader smoke on 2026-10-25 successfully fetched and parsed all 38,997 records, bulk ID `27bf3214-1271-490b-bdfe-c0be6c23d02e`, update `2026-10-25T09:01:57.491+00:00`, compressed size 25,108,904 bytes, SHA-256 `a1f17b0755da5cba940c9b1df71e758415e225ea9d97b9bf1bc699fedc3cfcc3`. Download compatibility is verified separately from embedding/import completion.

## Complete-document handling

This policy supersedes the initial card-length rejection described in the earlier vector/reranking slices. Card documents are stored unchanged in full. The application tokenizes without truncation and uses the tokenizer's offsets to create adjacent original-text windows. Every original character is covered, including all faces and trailing abilities. Each window is re-tokenized to verify its actual budget; splitting at a wordpiece boundary may require a smaller text span. No character-count estimate is used as the final token-length check.

BGE document windows reserve model special-token costs from the 512-token budget. Every window is encoded, normalized, and included in a token-count-weighted mean that is normalized again to produce one card vector. This keeps the distinct-card retrieval unit and one vector per card. The compatibility identity records immutable model revision, query instruction, normalization, maximum length, window policy, and aggregation. Existing embeddings prepared under the earlier rejection policy must be rebuilt. Queries keep the published BGE instruction and are explicitly rejected if the complete instructed query exceeds the model budget.

The cross-encoder reserves the complete query and pair special-token costs, then scores every document window under the remaining budget. The card score is the maximum window logit. A query leaving no evidence budget is rejected with a clear error. Each pair is checked before inference. The trace identifies this aggregation independently of the embedding model; changing the reranker never rebuilds card vectors.

These are application policies, not model-author quality claims. Mean aggregation can dilute an isolated ability, while max aggregation rewards a strong matching passage. The benchmark must measure those tradeoffs. Neither policy changes the complete evidence text supplied to the answer provider.

Embedding is batched (default 32 windows); optional `MAGIC_RAG_EMBEDDING_BATCH_SIZE` and `MAGIC_RAG_RERANKER_BATCH_SIZE` control inference batching. CPU is supported and full imports can take minutes. `OMP_NUM_THREADS` can limit CPU threading; execution settings are recorded in corpus metadata. GPU selection follows the existing model device settings. Datasets, model weights, and generated databases stay outside Git.

## Safe activation and verification

All normalization and embeddings finish before activation. Inside one SQLite transaction the service replaces cards, FTS5 data, vec0 data, compatibility metadata, and corpus identity; it validates counts and database integrity before committing. Any exception rolls back the whole replacement. Conversations and saved trace JSON remain in place, preserving their original corpus identity, source text, candidates, and selected evidence.

`uv run --python 3.11 pytest` covers first import, duplicate printings, all faces, Japanese printing/canonical fields, fractional values, successful replacement, source and embedding failures, missing identities, complete long documents, current HTTP metadata/gzip contract, truncated downloads, and an actual SQLite activation failure after both replacement indexes were written. All observations use the FastAPI boundary. `MAGIC_RAG_REAL_MODELS=1` enables separate real BGE/cross-encoder checks of long documents and oversized queries.

The real complete-corpus import/search smoke passed on 2026-10-25: all **38,997 distinct cards** activated in 833,067 ms (about 13 minutes 53 seconds) on Windows 10, x64 Python 3.11.4, CPU, `OMP_NUM_THREADS=4`, embedding batch size 32. SQLite 3.42.0/FTS5 and sqlite-vec 0.1.6 stored and searched the complete corpus. This runtime describes this device and configuration, not a general performance target.

The separate database was initially `%TEMP%/magic-rag-full.db` and was subsequently relocated with SQLite's backup API to the project's ignored `data/cards.db`. Its corpus identity is `scryfall-local:a1f17b0755da5cba940c9b1df71e758415e225ea9d97b9bf1bc699fedc3cfcc3`; its checksum matches the separately verified live export above. The BGE immutable revision was `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, and the independently loaded MiniLM revision was `233902d25c440f23af6f7d6e94d2946bac0bee0a`.

Real FastAPI searches passed in all four modes, including explicit blue/Creature/mana-value ≤1 constraints applied to every candidate stage. The canonical English card **Murgish Cemetery**, selected from a Japanese printing, was retrievable. **Magic and Minions // Magic and Minions (cont'd)** produced a 2,330-character, 539-token complete document: both faces' full source text remained in its trace and the real cross-encoder successfully scored its windows. Oversized queries still fail explicitly; the separate two-model long-input smoke passed as well. The session's detailed result is outside Git at `%TEMP%/magic-rag-full-smoke.json`. Retrieval compatibility and full-text coverage passed; Magic relevance is measured separately by the benchmark.
