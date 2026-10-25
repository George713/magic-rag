# Real full-corpus benchmark: 2026-10-25

Completed **80 measured retrieval calls** (20 questions × four modes), plus four separately recorded warmups, through the application's FastAPI benchmark boundary. No remote provider was called. This is a provisional comparison against bounded reviewed positives, not an exhaustive assessment of card relevance.

## Recorded configuration

- Corpus: 38,997 distinct cards from the complete Scryfall Oracle gzip JSONL export. Corpus ID `scryfall-local:a1f17b0755da5cba940c9b1df71e758415e225ea9d97b9bf1bc699fedc3cfcc3`; source SHA-256 is the suffix. All modes used this identity and identical effective filters/settings.
- Suite: `cards-v1-2026-10-25`, canonical suite hash `01197398c1cc752617f7259068b41bc091a139928da0f841d2fd05453e57a82c`. The preset was recorded before execution: cutoff 5, candidates 20/20, RRF 60, shortlist 40, evidence 5. Eighteen supported questions contribute quality scores; two unsupported probes contribute latency only.
- Embeddings: `BAAI/bge-small-en-v1.5`, revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`; normalized 384-dimensional vectors, instructed queries, complete-document windows of 510 content tokens with token-weighted normalized-mean aggregation. Overlength queries fail explicitly.
- Reranker: `cross-encoder/ms-marco-MiniLM-L6-v2`, revision `233902d25c440f23af6f7d6e94d2946bac0bee0a`; 512-token pair budget, query-budgeted complete-document windows, maximum window logit.
- Device: AMD Ryzen 7 5800X3D 8-Core Processor, 16 logical CPUs, Windows build 22621, CPU inference. `OMP_NUM_THREADS=4`, `MKL_NUM_THREADS=4`, observed Torch intra-op threads 4 and inter-op threads 8. Python 3.11.4, SQLite 3.42.0, sqlite-vec 0.1.6, SentenceTransformers 5.7.0, Torch 2.14.1, Transformers 5.20.2.
- One desktop run with cached models and fixed mode order. Warmup vector loading took about 7.50 seconds; it is excluded from measured-query latency. Background desktop load was not controlled. These measurements do not establish universal performance.

## Operational scores against the seed judgments

| Mode | MRR@5 | Binary nDCG@5 | Known-positive precision@5 | Retrieval median ms | Retrieval p95 ms |
|---|---:|---:|---:|---:|---:|
| Keyword | 0.4167 | 0.4759 | 0.1556 | 99.03 | 165.00 |
| Vector | 0.5972 | 0.5666 | 0.1556 | 213.78 | 226.65 |
| Hybrid | 0.5019 | 0.5245 | 0.1667 | 292.90 | 331.00 |
| Hybrid + reranker | 0.6667 | 0.6573 | 0.1889 | 870.82 | 1389.89 |

Reranking increased aggregate known-positive scores in this run and added latency. It did not improve every question: query 10's judged Viscera Seer appeared in vector/hybrid top five but fell outside the reranked top five. Query 7's Cultivate was recovered by reranking. Sakura-Tribe Elder (query 6) and Reclamation Sage (query 8) missed the top five in every mode. These misses and trade-offs are visible in the report rather than hidden by a blanket improvement claim.

## Pooled-candidate review and limitations

Reviewed the union of top-five candidate names across all four modes and checked several obvious unjudged alternatives against the original complete canonical source records. Examples:

| Query | Unjudged candidate | Source-grounded relevance |
|---|---|---|
| 10 | Woe Strider (`3adbd963-e85d-4569-963a-4472594f06f9`) | Sacrifices another creature to scry 1. |
| 10 | Fleshtaker (`14d5fdb3-14a3-461d-8515-a520c2c9e666`) | Offers a creature-sacrifice ability and scries when another creature is sacrificed. |
| 13 | Slobad, Goblin Tinkerer (`1f2d6cf4-b8f4-440f-ac08-ca47ada868ac`) | Red creature, mana value 2, sacrifices an artifact to grant indestructible. |
| 14 | Cut Down (`1b30210d-10e9-4703-8967-032063bb4f26`) and Dark Betrayal (`d3ebe9ae-108f-4d23-a236-35d632889cf8`) | Black instants of mana value 1 that destroy creatures under stated restrictions. The question did not require unrestricted removal. |
| 15 | Depopulate (`4a83c2fa-f2d2-4b86-8407-4269f127936d`) and No Witnesses (`0639bd82-084f-47d5-b158-05dfc29efa40`) | White sorceries of mana value 4 that destroy all creatures, with additional effects. |
| 16 | Workshop Assistant (`319ee221-bace-41e9-b386-6b528bd780c1`) | Colorless artifact creature, mana value 3, returns another artifact from graveyard to hand on death. |

The published seed scores intentionally remain unchanged after this review. These examples show why treating unjudged cards as zero can understate useful retrieval: query 14 has valid alternatives even where its known-positive score is zero. Before firmer conclusions, expand and version judgments using pooled review, then rerun all strategies against that new suite. No exhaustive recall, generated-answer correctness, or provider suitability is inferred here.

## Artifacts and reproduction

Raw report artifacts remain outside Git on the execution machine:

- `$env:TEMP/magic-rag-benchmark-20261025.json` — complete traces and provenance; SHA-256 `9593901ec60857569a7c2c7d4aff9bb185f8e97aab697660be37e2ba3f7e1465`.
- `$env:TEMP/magic-rag-benchmark-20261025.md` — inspectable comparison and per-question candidates.

The measured run reused the verified model environment from `.worktrees/issue-8/.venv/Scripts/python.exe`, set `PYTHONPATH` to the benchmark branch's `backend` directory, `MAGIC_RAG_DB` to `$env:TEMP/magic-rag-full.db`, CPU/thread settings above, and `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1`. It invoked `python -m magic_rag benchmark --output <temporary JSON path>`. The CLI calls the actual ASGI benchmark boundary, preserving FastAPI's AnyIO execution context. Use the durable [setup and repeatable invocation](evaluation.md) after worktrees are removed; no temporary worktree is required by the application.
