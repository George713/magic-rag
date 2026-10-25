"""Compare the application's retrieval modes against explicitly reviewed card judgments."""
from datetime import datetime, timezone
import math
import platform
import hashlib
import json
import os
import sqlite3
import sys
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
from pathlib import Path
from statistics import mean, median
from time import perf_counter

from typing import Literal

from fastapi import HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .filters import ExactFilters


MODES = ("keyword", "vector", "hybrid", "hybrid_rerank")
PRESET = {"keyword_candidates":20,"vector_candidates":20,"rrf_constant":60,"rerank_candidates":40,"evidence_limit":5}
JUDGMENT_POLICY = "Bounded reviewed positive judgments, not exhaustive relevance. Unjudged cards score zero operationally. Review pooled top-k candidates before drawing firm quality conclusions. Unsupported probes are excluded from quality denominators; related retrieval does not establish answer support."
METRIC_DEFINITIONS = {"mrr":"Reciprocal rank of the first known positive within cutoff; zero on a miss.",
                     "ndcg":"Binary discounted gain divided by ideal gain for min(known positives, cutoff).",
                     "known_positive_precision":"Known positives within cutoff divided by cutoff, including missing positions as zero."}


class Judgment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card_id: str
    name: str
    relevance: Literal[1] = 1
    rationale: str


class BenchmarkQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    category: str
    question: str
    filters: ExactFilters = Field(default_factory=ExactFilters)
    qrels: list[Judgment]
    unsupported: bool = False
    review: str

    @model_validator(mode="after")
    def consistent_judgments(self):
        if self.unsupported == bool(self.qrels):
            raise ValueError("Supported questions need reviewed positives; unsupported probes must have none.")
        if len({item.card_id for item in self.qrels}) != len(self.qrels):
            raise ValueError("A card may have only one relevance judgment per question.")
        return self


class BenchmarkSuite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    review: str
    source: dict
    questions: list[BenchmarkQuestion] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_questions(self):
        if len({question.id for question in self.questions}) != len(self.questions):
            raise ValueError("Benchmark question IDs must be unique.")
        return self


class BenchmarkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suite: BenchmarkSuite = Field(default_factory=lambda: BenchmarkSuite.model_validate_json(files("magic_rag").joinpath("benchmark_questions.json").read_text(encoding="utf-8")))
    cutoff: int = Field(default=5, ge=1, le=1000)
    settings: dict = Field(default_factory=lambda: dict(PRESET))
    warmup: bool = True


def quality_at_cutoff(cards, positive_ids, cutoff):
    relevant = [card["card_id"] in positive_ids for card in cards[:cutoff]]
    first = next((rank for rank, hit in enumerate(relevant, 1) if hit), None)
    dcg = sum(1 / math.log2(rank + 1) for rank, hit in enumerate(relevant, 1) if hit)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(len(positive_ids), cutoff) + 1))
    return {"mrr":1 / first if first else 0.0, "ndcg":dcg / ideal if ideal else 0.0,
            "known_positive_precision":sum(relevant) / cutoff}


def execution_environment():
    packages = {}
    for name in ("magic-rag", "fastapi", "sqlite-vec", "sentence-transformers", "torch", "transformers"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    processor = platform.processor()
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                processor = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except OSError:
            pass
    torch = sys.modules.get("torch")
    return {"python":platform.python_version(), "platform":platform.platform(), "machine":platform.machine(),
            "processor":processor, "cpu_count":os.cpu_count(), "sqlite":sqlite3.sqlite_version, "packages":packages,
            "device":os.environ.get("MAGIC_RAG_DEVICE", "cpu"),
            "reranker_device":os.environ.get("MAGIC_RAG_RERANKER_DEVICE", os.environ.get("MAGIC_RAG_DEVICE", "cpu")),
            "omp_num_threads":os.environ.get("OMP_NUM_THREADS"), "mkl_num_threads":os.environ.get("MKL_NUM_THREADS"),
            "torch_threads":torch.get_num_threads() if torch else None,
            "torch_interop_threads":torch.get_num_interop_threads() if torch else None}


def latency_summary(values):
    ordered = sorted(values)
    return {"median":median(ordered), "p95":ordered[math.ceil(0.95 * len(ordered)) - 1]}


def run_benchmark(request, search, search_request):
    try:
        prepared = {question.id:{mode:search_request(question=question.question, mode=mode,
                    filters=question.filters, settings={**PRESET,**request.settings}, generate_answer=False)
                    for mode in MODES} for question in request.suite.questions}
    except ValidationError as exc:
        raise HTTPException(422, "Invalid benchmark question, filters, or retrieval settings. " + "; ".join(error["msg"] for error in exc.errors())) from exc
    settings = next(iter(prepared.values()))["keyword"].settings.model_dump()
    if settings["evidence_limit"] < request.cutoff:
        raise HTTPException(422, "Evidence limit must be at least the evaluation cutoff.")
    questions = []
    models = {}
    corpus = None
    warmups = []

    def record_configuration(trace):
        nonlocal corpus
        if trace["corpus"] is None:
            raise HTTPException(409, "Import a corpus with compatible embeddings before running the four-mode benchmark.")
        if corpus is not None and trace["corpus"] != corpus:
            raise HTTPException(409, "Corpus changed during the benchmark. Repeat against one stable corpus.")
        corpus = trace["corpus"]
        for name, config in trace["models"].items():
            if name in models and models[name] != config:
                raise HTTPException(409, "Model configuration changed during the benchmark.")
            models[name] = config
    if request.warmup:
        first = request.suite.questions[0]
        for mode in MODES:
            started = perf_counter()
            trace = search(prepared[first.id][mode])
            record_configuration(trace)
            warmups.append({"mode":mode,"application_call_ms":(perf_counter()-started)*1000,"timings_ms":trace["timings_ms"]})
    for question in request.suite.questions:
        runs = {}
        for mode in MODES:
            started = perf_counter()
            trace = search(prepared[question.id][mode])
            elapsed = (perf_counter() - started) * 1000
            record_configuration(trace)
            runs[mode] = {"metrics":None if question.unsupported else quality_at_cutoff(trace["selected_evidence"], {item.card_id for item in question.qrels}, request.cutoff),
                          "application_call_ms":elapsed, "trace":trace}
        questions.append({**question.model_dump(), "runs":runs})
    aggregates = {}
    for mode in MODES:
        runs = [question["runs"][mode] for question in questions]
        judged = [run for run in runs if run["metrics"] is not None]
        aggregates[mode] = {"mean_metrics":{metric:mean(run["metrics"][metric] for run in judged) for metric in judged[0]["metrics"]} if judged else None,
                            "application_call_ms":latency_summary([run["application_call_ms"] for run in runs]),
                            "retrieval_ms":latency_summary([run["trace"]["timings_ms"]["retrieval"] for run in runs])}
    suite_json = json.dumps(request.suite.model_dump(), sort_keys=True, ensure_ascii=False).encode("utf-8")
    return {"report_version":1, "created_at":datetime.now(timezone.utc).isoformat(), "suite_version":request.suite.version,
            "suite_sha256":hashlib.sha256(suite_json).hexdigest(), "source":request.suite.source,"suite_review":request.suite.review,
            "judgment_policy":JUDGMENT_POLICY, "metric_definitions":METRIC_DEFINITIONS,
            "settings":settings, "warmups":warmups,"measurement_policy":"One measured trial per question/mode in fixed mode order; warmups excluded. Application-call latency excludes HTTP transport and includes model configuration access. Nearest-rank p95. No universal performance claim.",
            "mode_order":MODES,
            "cutoff":request.cutoff, "quality_question_count":sum(not question.unsupported for question in request.suite.questions), "corpus":corpus,"models":models,
            "environment":execution_environment(), "questions":questions, "aggregates":aggregates}


def render_markdown(report):
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = ["# Known-positive retrieval benchmark", "", f"Suite `{report['suite_version']}` · cutoff {report['cutoff']} · {report['quality_question_count']} supported questions · {len(report['questions']) - report['quality_question_count']} unsupported probes", "",
             JUDGMENT_POLICY, "", "| Mode | MRR | nDCG | Known-positive precision | Retrieval median / p95 ms | Application median / p95 ms |",
             "|---|---:|---:|---:|---:|---:|"]
    for mode, aggregate in report["aggregates"].items():
        metrics = aggregate["mean_metrics"]
        scores = [f"{metrics[key]:.4f}" if metrics else "—" for key in ("mrr", "ndcg", "known_positive_precision")]
        retrieval = aggregate["retrieval_ms"]
        elapsed = aggregate["application_call_ms"]
        lines.append(f"| {mode} | {' | '.join(scores)} | {retrieval['median']:.2f} / {retrieval['p95']:.2f} | {elapsed['median']:.2f} / {elapsed['p95']:.2f} |")
    lines += ["", report["measurement_policy"], "", "## Reproduction context", "", "```json", json.dumps({key:report[key] for key in ("created_at", "suite_sha256", "source", "corpus", "models", "settings", "environment", "warmups", "metric_definitions")}, indent=2, ensure_ascii=False), "```", "", "## Per-question candidates", "", "Full branch candidates, scores, selected evidence, filters, and timings are retained in the JSON report. Unjudged candidates below need pooled review before firm comparisons.", "", "| Question | Mode | MRR | nDCG | Top selected cards |", "|---|---|---:|---:|---|"]
    for question in report["questions"]:
        lines.append(f"| **{cell(question['id'])}: {cell(question['question'])}** | | | | |")
        for mode, run in question["runs"].items():
            metrics = run["metrics"]
            scores = [f"{metrics[key]:.4f}" if metrics else "excluded" for key in ("mrr", "ndcg")]
            names = "; ".join(card["name"] for card in run["trace"]["selected_evidence"][:report["cutoff"]]) or "No candidates"
            lines.append(f"| {cell(question['id'])} | {mode} | {' | '.join(scores)} | {cell(names)} |")
    return "\n".join(lines) + "\n"


def write_report(report, output):
    output = Path(output)
    if output.suffix.lower() != ".json":
        raise ValueError("Benchmark output must use a .json extension; Markdown is written alongside it.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    markdown = output.with_suffix(".md")
    markdown.write_text(render_markdown(report), encoding="utf-8")
    return {"json":str(output.resolve()), "markdown":str(markdown.resolve())}


def register_evaluation(app, search, search_request):
    @app.post("/api/benchmark")
    def benchmark(request: BenchmarkRequest, format: Literal["json", "markdown"] = "json"):
        report = run_benchmark(request, search, search_request)
        return PlainTextResponse(render_markdown(report), media_type="text/markdown") if format == "markdown" else report
    app.state.benchmark = benchmark
