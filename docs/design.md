# Magic RAG proof of concept

Status: architecture decisions accepted; implementation has not begun. Provider suitability and dataset compatibility still require verification.

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
- Corpus: target all distinct cards in English with current canonical text; collapse repeated printings. Scryfall is the proposed source pending export verification. Artwork variants, translations, prices, and historical wording are deferred.
- Evidence: answers cite retrieved cards and acknowledge conclusions unsupported by the retrieved evidence.
- Evaluation: approximately 20 benchmark questions comparing keyword-only, vector-only, hybrid, and hybrid-plus-reranker retrieval. Evaluate useful cards near the top and retrieval latency.
- Conversations: persist across restarts; support starting and deleting conversations.
- Retrieval unit (Q11): one searchable document per card, including name, mana cost, types, colors, and card text across all faces. Keep numeric and categorical fields separately for filtering.
- Exact constraints (Q13): explicit interface filters for color, card type, and mana value; enforce during retrieval and display in the inspector. Automatic extraction from conversational text is deferred.

## Accepted retrieval and ingestion decisions

- Q12: BM25 keyword search and dense vector search, merged with reciprocal rank fusion, followed by a separate cross-encoder reranker. Accepted after explanation.
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

SQLite comparison: [FTS5](https://www.sqlite.org/fts5.html) supports full-text keyword retrieval and BM25 ranking. [sqlite-vec](https://alexgarcia.xyz/sqlite-vec/) adds vector search as a separate extension, including Python bindings. Choosing SQLite for all persistence would require maintaining the text and vector search tables and composing hybrid retrieval in the application. Neither database eliminates the separate embedding or cross-encoder models. SQLite runtime/extension compatibility has not been tested here.

LanceDB was considered for integrated keyword/vector retrieval and rejected in favor of one SQLite persistence system. SQLite FTS5 and sqlite-vec runtime compatibility remain to be tested during implementation.

## Verified integration facts

Checked 2026-10-25:

- [OpenCode inference API](https://opencode.ai/v2/docs/console/api/inference/) documents direct authenticated API requests, including use from other clients.
- [OpenCode Go](https://opencode.ai/v2/docs/console/go/) describes coding agents as its intended clients and requests typical coding-agent traffic. A Magic chat application's suitability is not established merely by API compatibility. Keep this as an unresolved provider constraint.
- No Go embedding or dedicated reranking API was identified in the reviewed documentation; the accepted local components do not depend on these endpoints.
- Scryfall bulk-data documentation could not yet be fetched (HTTP 403); dataset details remain under investigation.

## Decision records

Record accepted terminology in the root glossary as it is resolved. Create ADRs only for accepted architectural decisions with meaningful trade-offs and meaningful reversal costs.
