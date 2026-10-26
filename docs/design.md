# Magic RAG proof of concept

Status: local retrieval, persistent conversations, provider boundaries, streaming, filters, and corpus import are implemented. Scryfall's current export contract and local model execution have been verified. OpenCode Go workload suitability remains unresolved; deterministic provider tests do not establish live subscription support.

## Requested outcome

A toy project for gaining hands-on experience with retrieval augmented generation using Magic: The Gathering data. The requested experience is a ChatGPT-style chat interface, a local database containing source data and embeddings, hybrid retrieval, and a reranker. The intended answer-generation provider is the user's OpenCode Go subscription; integration feasibility is being researched.

## Design tree

- Learning outcome and what a successful demonstration must show.
  - Evaluation examples and comparison of retrieval strategies.
- Supported Magic questions and evidence sources.
  - Card identity, printings, rulings, and game rules.
  - Ingestion scope, document boundaries, and updates.
- Meaning of local operation and allowed external services.
  - Database, embedding model, reranker, and hardware constraints.
- Audience and deployment scope.
  - Conversation persistence and access controls.
- Implementation language preferences.
  - Application structure and integration approach.
- OpenCode Go integration feasibility (research pending).
  - Answer model, credentials, usage constraints, and failure behavior.

## Accepted foundations

- Learning outcome: inspect keyword and vector retrieval results, their combination, and the changes made by reranking in an inspector alongside chat.
- Initial questions: card discovery and card explanations. Authoritative rules interactions, deck optimization, and prices are deferred.
- Local operation: database, embedding model, and reranker run on the user's computer. Answer generation uses a remote provider; OpenCode Go remains the desired provider, subject to suitability.
- Audience: a single user running the application on Windows.
- Interface: SvelteKit.
- Backend: the user delegated Python versus Node.js. Python is selected for the local model and retrieval work.
- Provider flexibility: answer generation is configurable. Go is preferred but remains subject to suitability; no alternative paid service is selected.
- Corpus: import distinct cards with current canonical English text from the verified Scryfall oracle-card export; collapse repeated printings and retain every face. Artwork variants, translations, prices, and historical wording are deferred.
- Evidence: answers cite retrieved cards and acknowledge conclusions unsupported by the retrieved evidence.
- Evaluation: approximately 20 benchmark questions comparing keyword-only, vector-only, hybrid, and hybrid-plus-reranker retrieval. Evaluate useful cards near the top and retrieval latency.
- Conversations: persist across restarts; support starting and deleting conversations.
- Retrieval unit (Q11): one searchable document per card, including name, mana cost, types, colors, and card text across all faces. Keep numeric and categorical fields separately for filtering.
- Exact constraints (Q13): explicit interface filters for color, card type, and mana value; enforce during retrieval and display in the inspector. Automatic extraction from conversational text is deferred.

## Accepted retrieval and ingestion decisions

- Q12: BM25 keyword search and dense vector search, merged with reciprocal rank fusion, followed by a separate cross-encoder reranker. Accepted after explanation.
- Exact full-name matches to the actual retrieval query take priority in all retrieval modes, ignoring capitalization and surrounding whitespace. Apply this before candidate, reranker-shortlist, and evidence limits, respecting filters and retaining raw scores. Other cards retain the existing relevance ordering.
- Q14: BAAI/bge-small-en-v1.5 embeddings and cross-encoder/ms-marco-MiniLM-L6-v2 reranking as replaceable baselines. Accepted after explanation. No project-specific quality or memory measurements have been made.
- Q15: manual, versioned ingestion with replacement-index activation only after successful completion. Ingestion includes downloading, normalizing, embedding, storing, and indexing the corpus; it applies to initial population and later refreshes. Accepted after clarification.

## Retrieval proposal rationale

BM25 ranks lexical matches using term rarity, diminishing returns for repetition, and document-length normalization. It is proposed as a transparent, training-free complement to semantic similarity for card names and Magic terminology. Reciprocal rank fusion combines positions from the two result lists without treating their different raw score scales as comparable. A separate cross-encoder then reads each query together with each candidate card to score relevance; unlike stored card embeddings, these scores depend on the current query. This extra stage is a hypothesis to evaluate, not a guarantee of improvement.

The proposed embedding model is an English retrieval baseline with 384-dimensional vectors and a 512-token input limit ([model card](https://huggingface.co/BAAI/bge-small-en-v1.5)). Its published safetensors weights occupy about 133 MB. The proposed reranker is an English passage-ranking baseline with about 90.9 MB of published safetensors weights ([model files](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2/tree/main)). Both are small enough for CPU inference; GPU acceleration is optional. File sizes are not runtime memory requirements: runtime libraries, activations, sequence lengths, and batching add memory. Actual memory and latency must be measured locally. Neither model is established as best for Magic queries. Token-length validation must prevent silently dropping card faces or abilities.

Ingestion does not train the models. It prepares and embeds card data with a pretrained model and builds searchable indexes. At question time, only the search query needs a new embedding; the stored card embeddings are reused. Changing embedding models requires rebuilding the card embeddings; changing only the reranker does not.

The same embedding model and compatible configuration encode stored cards and incoming search queries into the same vector space, with the appropriate query/document formatting. Vector search compares query and stored vectors using a similarity metric; it does not require another trained model. BM25, RRF fusion, and deduplication by card identity likewise require no trained model. The separate cross-encoder reranker consumes query/card-text pairs rather than stored card vectors. The answer-generation model is a third, remote model with a different role.

## Accepted persistence decision

- Q16: use SQLite as the sole database for cards, embeddings, conversations, and retrieval traces. FTS5 provides BM25 keyword search; sqlite-vec provides vector search. Python combines the ranked results with RRF and applies the separate cross-encoder reranker. Run SQLite embedded in the Python process with a local database file; Docker and a database server are unnecessary.

## Accepted application decisions

- Q17: SvelteKit chat interface and server routes forwarding to a local Python FastAPI service. Python owns retrieval, model inference, ingestion, answer-provider calls, and persistence. Provider credentials remain server-side.
- Q18: use conversation history in an additional remote-model call to produce a standalone retrieval query for follow-ups. Show the rewritten query in the inspector. Explicit filters persist until changed. This adds model usage and latency.
- Q19: stream generated answers with a Stop button. Retrieval and its inspector remain usable independently when the remote model is unconfigured or unavailable. Show provider errors clearly and retain retrieved results.

## Accepted chat interface extension

Accepted during the 2026-10-25 through 2026-10-26 design interview. The user requested specification publication and confirmed the proposed browser and API integration testing seams on 2026-10-26.

Tracked in [specification #15: Conversational card chat with persistent filters and image assets](https://github.com/George713/magic-rag/issues/15).

- Use a ChatGPT-style layout: previous conversations and New chat on the left, the conversation transcript and composer in the center, and filters on the right. Side panels can collapse on smaller screens.
- Support card discovery, card explanations, and conversational follow-ups, with answers grounded in retrieved cards. The card presentation refinement below supersedes the original requirement for visible citation and asset-reference links in answers. Deck optimization and authoritative rules rulings remain deferred.
- Keep checkbox controls for filters and add a separate Legendary checkbox. Checked means only legendary cards are eligible; unchecked imposes no legendary restriction. Combine it with the other explicit filters and apply the selected filters to the next submitted message.
- Sending a message automatically retrieves evidence and generates a streamed answer, with a Stop button.
- Put the retrieval inspector in an expandable Retrieval details section beneath each answer; reserve the right sidebar for filters.
- Preserve existing matching semantics: colors match the exact selected set, and selected card types must all be present. Legendary adds another requirement.
- Persist each conversation's current filters independently. Historical turns retain their original filter snapshots; viewing their retrieval details does not alter the current controls. This replaces the existing behavior of restoring controls when a historical turn is selected.
- OpenCode Go remains the preferred answer provider. Its current official guidance still requests typical coding-agent traffic, so suitability for card assistance remains unresolved; checking its API does not settle that constraint. Rechecked [Go workload guidance](https://opencode.ai/v2/docs/console/go/#where-can-i-use-it) on 2026-10-25. No live request or alternative paid provider has been authorized by this design interview.
- Use a dark theme only; no light theme or theme switcher is required.
- Initial controls: New chat, Delete chat, Send, Stop, and Copy answer. Message editing, answer regeneration, and conversation branching are deferred.
- Each response supports optional model-written text and a separate card-asset section beneath it. Text-only, assets-only, and text-plus-assets responses are valid; explanatory prose and full card text are not mandatory alongside images.
- The model selects card assets from retrieved evidence. The application resolves their image URLs from source metadata rather than accepting model-invented URLs.
- Display card images directly in the asset section. Clicking an image opens an enlarged, centered view with a close control. A separate Open image link is not required.
- Use one representative printing per distinct card, with both face images available for double-faced cards. Selecting alternate printings/artwork is deferred.
- New conversations start without filter restrictions; existing conversations remember their current filters across application restarts.
- On provider failure, preserve retrieved cards and show a clear error. When no cards match, explain this and suggest adjusting the query or filters, without changing the selected filters automatically.
- Feasibility: Scryfall's [official card fields](https://github.com/scryfall/api-types/blob/main/src/objects/Card/CardFields.ts) include a card-page URL and optional image URLs at card or face level. These can support external links and previews without generated URLs from the answer model. A preview represents a printing, while retrieval and citations continue to identify distinct cards.
- Live OpenCode Go workload suitability remains an integration uncertainty. The accepted interface and response behavior do not establish that the preferred provider supports this use case.

SQLite comparison: [FTS5](https://www.sqlite.org/fts5.html) supports full-text keyword retrieval and BM25 ranking. [sqlite-vec](https://alexgarcia.xyz/sqlite-vec/) adds vector search as a separate extension, including Python bindings. The implementation maintains both indexes and composes hybrid retrieval in the application. Both local models remain separate components. Windows runtime/extension compatibility is verified by real SQLite integration tests and local-model smoke checks.

LanceDB was considered for integrated keyword/vector retrieval and rejected in favor of one SQLite persistence system. The implemented SQLite FTS5 and sqlite-vec path requires no database service or Docker.

## Verified integration facts

Checked 2026-10-25:

- [OpenCode inference API](https://opencode.ai/v2/docs/console/api/inference/) documents direct authenticated API requests, including use from other clients.
- [OpenCode Go](https://opencode.ai/v2/docs/console/go/) describes coding agents as its intended clients and requests typical coding-agent traffic. A Magic chat application's suitability is not established merely by API compatibility. Keep this as an unresolved provider constraint.
- No Go embedding or dedicated reranking API was identified in the reviewed documentation; the accepted local components do not depend on these endpoints.
- Scryfall live metadata and complete download now work with identifying headers. The current `oracle_cards` contract supplies `jsonl_download_uri` and `compressed_size` for gzip JSON Lines; canonical `oracle_id` identifies distinct cards. The verified download has 38,997 records. [Corpus import and provenance](corpus-import.md) records the current contract, canonical-field handling, complete-document windows, atomic activation, and smoke results.
- Windows Python 3.11.4 successfully loads SQLite FTS5 and sqlite-vec 0.1.6. Real BGE and MiniLM CPU smoke checks pass, including document windows and explicit oversized-query errors. Compatibility identities include immutable revisions and window/aggregation policy. [Vector search](vector-search.md) and [reranking](reranking.md) record execution and verification details.

## Accepted chat follow-up fixes

Confirmed in the 2026-10-26 interview; tracked in [#23](https://github.com/George713/magic-rag/issues/23).

- Each conversation immediately saves its current search mode, including unsent changes, and restores it on reopening and application restart. New conversations default to keyword search. Existing conversations inherit the latest saved turn's mode when the preference is introduced; historical modes remain attached to their original turns.
- Each answer has a separate Retrieved evidence disclosure, closed by default alongside Retrieval details. Selected card assets stay visible beneath the answer. The card presentation refinement below supersedes the original answer citation and asset-reference links that opened the turn's evidence. No-match guidance remains visible without opening either disclosure.
- Repair missing source imagery in the existing corpus and saved card assets/evidence, preserving selected card identities, historical text, ranks, filters, and generation content. Preserve existing image snapshots. Use source-provided representative-printing images, both faces where applicable, and the existing enlargement interaction.
- The repair acquires presentation metadata separately from embedding/index preparation and applies missing metadata atomically. A failed acquisition or write preserves previous data. It does not change the active corpus identity or require rebuilding local-model indexes.

## Accepted chat card presentation refinement

Accepted in the 2026-10-26 grill-with-docs interview and carried into the requested specification stage. Browser testing and the missing-image fallback were confirmed during specification preparation. These decisions describe intended behavior, not completed implementation.

Tracked in [specification #25: Simplify chat card rows and frameless image enlargement](https://github.com/George713/magic-rag/issues/25).

- Remove the answer's Sources line and the additional linked card name above each card asset. Preserve answer text, Retrieved evidence, and Retrieval details, including their existing content and interactions.
- Show all selected card images for an answer in one horizontal row, preserving the existing card and face order. Include both face images for double-faced cards in the same row. Use small gaps and readable thumbnail sizes, with horizontal scrolling when the row exceeds the available width, including on mobile. Center each image's name beneath it.
- Wherever an image is enlarged, show the centered card image without an interface frame, border, or background. Keep the darkened backdrop and center the name beneath the image as floating text. Preserve source artwork and printed card borders; processing white pixels embedded in source imagery is outside this change.
- Place a semi-transparent X over the enlarged card's top-right corner. Clicking anywhere, including the image, name, or backdrop, closes the enlarged view. Escape also closes it; closing restores keyboard focus to the thumbnail that opened it.
- Apply the enlargement presentation consistently to answer assets and images inside Retrieved evidence. The single-row layout requirement applies to the answer's selected card assets.
- Keep a plain, unlinked card name when a selected asset has no image metadata. Preserve readable image-load errors and access to evidence.
- Verify at the existing Playwright chat browser seam with deterministic responses and realistically sized images. Cover desktop/mobile overflow, captions, both faces, saved chats, all closing interactions, and focus restoration; inspect screenshots for the transparent presentation and dark backdrop. Replace assertions requiring the removed links. No new backend testing seam is needed.

## Decision records

Record accepted terminology in the root glossary as it is resolved. Create ADRs only for accepted architectural decisions with meaningful trade-offs and meaningful reversal costs.
