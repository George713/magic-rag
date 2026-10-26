# Local vector search

The complete-document window policy in [corpus-import.md](corpus-import.md) supersedes the initial long-card rejection below. Queries still reject overlength; existing embeddings require rebuilding for the updated document policy.

Keyword mode needs no model download. To add local BGE embeddings to the controlled sample, use PowerShell from the repository root:

```powershell
uv sync --extra models --python 3.11
uv run --extra models --python 3.11 python -m magic_rag sample-vectors
uv run --extra models --python 3.11 python -m magic_rag serve
```

Start SvelteKit as described in [running.md](running.md), choose **Vector · local embeddings**, and submit a self-contained description. Model acquisition needs internet access once; Hugging Face caches downloaded weights outside Git by default. The first request may take longer while the model loads. `sample` intentionally installs keyword-only sample data and removes previous sample embeddings; `sample-vectors` builds both branches. Failed model acquisition or embedding does not activate a partially refreshed sample.

The baseline is `BAAI/bge-small-en-v1.5`, 384 dimensions, normalized vectors, cosine distance. Lower distances rank first. SQLite stores card text and vectors in the same database; the actual search uses a sqlite-vec `vec0` virtual table, not a Python substitute. Extension loading is disabled immediately after the packaged extension loads. sqlite-vec is pinned to 0.1.6. The service reports actionable startup errors if the runtime cannot load it.

The model's recommended instruction, `Represent this sentence for searching relevant passages: `, prefixes queries only; complete readable card documents receive no prefix. The compatibility identity records model, immutable Hugging Face revision, dimensions, normalization, instruction, token budget, and input policy. A running model must match the stored identity exactly; mismatches require re-ingestion. Changing the execution device alone does not change encoding identity.

CPU is the supported default. `MAGIC_RAG_DEVICE=cuda` requests a CUDA-capable PyTorch runtime and compatible GPU; otherwise keep `cpu`. `MAGIC_RAG_EMBEDDING_REVISION` optionally selects a Hugging Face revision; the actual immutable snapshot hash is recorded. Dependencies in `uv.lock` reproduce the tested runtime. The default installation excludes ML libraries; install `--extra models` only when using real local models.

Inputs are tokenized without truncation, including special tokens and the query instruction, before inference. Inputs exceeding the model's 512-token budget raise an explicit error. No faces or abilities are silently discarded. This slice rejects long inputs; complete-corpus chunk handling belongs to #8. Trace output records the model/configuration, distance convention, vector candidates and scores, stage latency, selected readable evidence, and corpus identity. Vector failures leave keyword retrieval available.

## Validation

```powershell
uv run --python 3.11 pytest
cd web
npx playwright test --config playwright.vector.config.ts
```

Deterministic model substitutes verify API ranking, provenance, missing/incompatible vectors, and model errors against real isolated SQLite FTS5 and sqlite-vec. The browser check uses a controlled model and separate ports 8103/5203. It establishes presentation, not semantic quality.

Separate real-model smoke (from repository root):

```powershell
$env:MAGIC_RAG_REAL_MODELS = '1'
uv run --extra models --python 3.11 pytest backend/tests/test_real_models.py -s
Remove-Item Env:MAGIC_RAG_REAL_MODELS
```

Passed 2026-10-25 on Windows 10, x64 Python 3.11.4, SQLite 3.42.0, sqlite-vec 0.1.6, SentenceTransformers 5.7.0, PyTorch 2.14.1, Transformers 5.20.2, CPU. The smoke embeds all sample documents, performs vector retrieval through FastAPI, verifies immutable revision/configuration, and rejects oversized card/query inputs before inference. It does not establish Magic-specific relevance; that remains benchmark work.

Primary references: [BGE model card](https://huggingface.co/BAAI/bge-small-en-v1.5), [sqlite-vec Python integration](https://alexgarcia.xyz/sqlite-vec/python.html).
