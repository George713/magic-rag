# Reviewed retrieval benchmark

The packaged [twenty-question suite](../backend/magic_rag/benchmark_questions.json) contains exact names, paraphrased abilities, all-face discovery, exact constraints, a colors-versus-color-identity case, and two unsupported requests. Twenty-five positive card judgments were reviewed against complete canonical card text from the recorded Scryfall snapshot and independently checked during implementation. Each judgment includes its rationale. Labels come from source-text review, not generated answers.

These are **bounded known positives, not exhaustive relevance judgments** over the entire corpus. Unjudged results count as zero for operational scores. Pool the top results from all modes and review plausible alternatives before drawing firm quality conclusions. Exact-name questions target one canonical card; broader questions can have additional relevant cards absent from the seed judgments.

## Preset and metrics

Fixed before the recorded run: cutoff **5**, keyword/vector candidate counts **20/20**, RRF constant **60**, reranker shortlist **40**, and selected evidence limit **5**. All modes use the same corpus, questions, explicit filters, and effective retrieval settings through the existing application search handler.

| Measure | Definition |
|---|---|
| MRR@5 | Reciprocal rank of the first known positive in the top five; zero if absent. |
| Binary nDCG@5 | Sum of `1 / log2(rank + 1)` at known-positive positions, divided by ideal gain for the smaller of five and the number of known positives. |
| Known-positive precision@5 | Number of known positives in the top five divided by five, including unfilled positions as zero. |
| Latency | Per-query application-call and retrieval-stage milliseconds; aggregate median and nearest-rank p95. |

Quality means cover **18 supported questions**. The two unsupported probes retain their candidates and latency but have null quality metrics and are excluded from quality denominators. Related cards are not evidence for current prices or universal tournament guarantees; nearest-neighbor retrieval need not be empty. This retrieval benchmark does not evaluate generated-answer truth or provider refusal behavior.

One warmup per mode uses the first question and is recorded separately. Each question/mode then has one measured call in fixed mode order. Application-call timing excludes HTTP transport and includes model/configuration access; retrieval-stage timing comes from the trace. Loading remains visible in warmup timings. Use `--no-warmup` to include initial loading in first measured calls. No universal speed or reranking-superiority claim follows from one device and one trial.

## Run and inspect

Use the [verified model setup](vector-search.md) and [complete corpus import](corpus-import.md). Stop other Python processes using the database, finish ingestion, and set the same database/model configuration in the benchmark terminal. For the recorded CPU policy:

```powershell
$env:MAGIC_RAG_DB = '<path to activated corpus.db>'
$env:MAGIC_RAG_DEVICE = 'cpu'
$env:OMP_NUM_THREADS = '4'
$env:MKL_NUM_THREADS = '4'
uv run --python 3.11 --extra models python -m magic_rag benchmark --output reports/retrieval-benchmark.json
```

The CLI writes JSON and a sibling Markdown report outside version control. JSON contains every question, reviewed qrel, actual filter, branch/fused/reranked candidates and scores, selected evidence, timings, corpus metadata, model revisions/configuration, suite hash, effective settings, warmups, and execution environment. Markdown presents aggregate quality/latency and per-question selected-card names. Read the bounded-judgment caveat before interpreting differences, then inspect missed known positives and plausible unjudged cards in the full traces.

`--benchmark-suite <json>`, `--settings <json>`, and `--cutoff <integer>` support explicit alternate experiments. Record a new suite version when judgments change. The evidence limit must cover the cutoff. Invalid or contradictory judgments fail before scoring; a corpus/model change during a run aborts comparison rather than mixing provenance. No conversations or generated answers are created.

`POST /api/benchmark` accepts `{}` for the default suite or `{suite, cutoff, settings, warmup}`. Add `?format=markdown` for a readable report response. It reuses the same retrieval handler as `POST /api/search`. Do not refresh the corpus during evaluation. This endpoint can take time while local models load and score candidates.

## Verification

`uv run pytest backend/tests/test_evaluation.py` uses the FastAPI seam with isolated real SQLite/sqlite-vec and controlled embedding/reranking providers. Independently worked examples check rank-two reciprocal rank and discounted gain, reranking changes, empty rankings, exact filters, unsupported exclusions, input validation, and report provenance. Deterministic substitutes establish contract behavior, not Magic relevance. The real full-corpus benchmark is documented separately once completed.
