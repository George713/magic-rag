# Inspect local reranking

Prepare sample embeddings using [vector-search.md](vector-search.md), start both processes, and choose **Hybrid + cross-encoder**. The API mode name is `hybrid_rerank`. This adds an independent local `cross-encoder/ms-marco-MiniLM-L6-v2` pass after reciprocal rank fusion. It reads the actual query paired with each shortlisted card's readable document, including its name, properties, and all retained face text.

Expand **Retrieval settings** to change **Reranker shortlist** (default 40) and **Evidence limit** (default 8), alongside the branch and fusion controls. The fused list remains intact in the trace; only its first `rerank_candidates` cards reach the cross-encoder. Selected evidence follows the reranked order, up to the evidence limit. Other modes bypass the reranker entirely.

The inspector shows raw branch candidates, the original fused order, reranker scores, final order, original fused positions, promotions/demotions, selected evidence, effective settings, and stage timings. Cross-encoder scores are unbounded relevance logits, with higher values ranking first; they are not probabilities or comparable to fusion/BM25/distance scores. Exact score ties use canonical card identity. Each reranked card retains `fused_rank`, `fusion_score`, contributing branch `signals`, final `rank`, and signed `rank_change` (positive means promoted).

The default execution device is CPU. The optional `MAGIC_RAG_RERANKER_DEVICE` overrides `MAGIC_RAG_DEVICE` for this model; use `cuda` only with a compatible GPU/PyTorch installation. `MAGIC_RAG_RERANKER_REVISION` can select a model revision; the adapter resolves and loads its immutable snapshot hash. The trace records embedding and reranker identities separately. Replacing only the reranker requires no card re-embedding.

Install optional inference dependencies with `uv sync --extra models --python 3.11`. First use downloads model weights to the Hugging Face cache outside Git. Every query/document pair is tokenized without truncation, counting both texts and special tokens against the model's 512-token limit. Overlength input is rejected with an explicit error before inference. Complete-corpus chunk coverage is #8; this slice never silently drops abilities to fit. Reranker errors leave the other retrieval modes usable.

## Verification

```powershell
uv run --python 3.11 pytest
cd web
npx playwright test --config playwright.reranking.config.ts
```

Deterministic API tests use real isolated FTS5/sqlite-vec and substitute only models. They check changed evidence selection, before/after ranks, unchanged fused results and branch signals, shortlist/evidence limits, bypass modes, replacing the reranker without rebuilding embeddings, invalid scores, and explicit pair-limit errors. The browser suite reserves ports 8105/5205 and verifies the inspector and controls.

Separate real-model smoke:

```powershell
$env:MAGIC_RAG_REAL_MODELS = '1'
uv run --extra models --python 3.11 pytest backend/tests/test_real_models.py -k cross_encoder -s
Remove-Item Env:MAGIC_RAG_REAL_MODELS
```

Passed on 2026-10-25 on Windows 10, Python 3.11.4, CPU, SentenceTransformers 5.7.0/PyTorch 2.14.1/Transformers 5.20.2. The smoke uses real BGE embeddings and the real cross-encoder through FastAPI, verifies separate immutable identities, and rejects oversized card/query pairs. Magic-specific relevance remains benchmark work; this does not establish that reranking improves every query.

Primary references: [model card](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2), [CrossEncoder API](https://www.sbert.net/docs/package_reference/cross_encoder/model.html).
