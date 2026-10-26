# Inspect hybrid search

All search modes prioritize an exact full card name matching the actual retrieval query, ignoring capitalization (Unicode case folding) and surrounding whitespace. This priority applies before candidate limits, fusion shortlisting, reranking, and evidence selection, while respecting explicit filters. A split card whose full name differs is not an exact match. Nonexact matches retain their usual score ordering and card-identity tie-breaks. Vector retrieval includes eligible exact-name cards even when they would fall outside the nearest-neighbor shortlist, without exceeding the configured candidate limit. No reimport or re-embedding is required.

Raw BM25, cosine-distance, fusion, and reranker scores remain unchanged; because exact-name priority precedes score, displayed scores need not be monotonic. The trace records this rule in `settings.name_priority`.

After [preparing sample embeddings](vector-search.md), choose **Hybrid · rank fusion** in the search interface. The keyword and vector branches run independently against the same active SQLite corpus and query. The inspector keeps both candidate lists and a separate fused ranking. Selected evidence follows the fused ranking and contains one entry per canonical card identity.

Reciprocal rank fusion adds `1 / (rrf_constant + branch_rank)` for each branch containing a card. Branch ranks start at 1; the default constant is 60. A card appearing in only one branch receives only that contribution. An empty branch contributes nothing. Fused scores sort descending; canonical card identity resolves exact ties. Raw BM25 and cosine-distance values are retained as branch signals, never mixed numerically with one another or with fusion scores. Both raw conventions sort ascending. The inspector labels each scale explicitly.

Expand **Retrieval settings** to change keyword/vector candidate limits, the fusion constant, or the evidence limit. Defaults are 20 / 20 / 60 / 8; these are starting settings, not fixed quality targets. Candidate and evidence counts accept 1–1000 and the fusion constant accepts 0–10000. The trace records effective settings, each branch's elapsed time, fusion time, original question, actual query, corpus/model identity, all candidates, fused ranks, contributing branch ranks/raw scores, and selected evidence. Pure keyword or vector mode uses the corresponding branch and evidence limit, bypassing fusion.

Equivalent API example:

```json
{"question":"Sol Ring","mode":"hybrid","settings":{"keyword_candidates":20,"vector_candidates":20,"rrf_constant":60,"evidence_limit":8}}
```

`stages.keyword` and `stages.vector` contain raw candidates. `stages.fused` contains deduplicated candidates whose `score` is the fusion score and whose `signals` dictionary preserves only the branches that found that card, each as `{rank, score}`. `rank` on a fused card is its new position. The selected evidence copies those cards without changing identity or readable text.

Verification uses FastAPI with real isolated FTS5/sqlite-vec indexes and a deterministic embedding substitute. It covers branch overlap, single-branch candidates, exact fusion ties, empty lexical results, configurable limits, and invalid settings. Browser presentation is checked with:

```powershell
cd web
npx playwright test --config playwright.hybrid.config.ts
```

This browser suite reserves ports 8104/5204 and does not require model downloads. Deterministic fusion checks establish ranking behavior, not Magic relevance. The later benchmark compares quality across modes.
