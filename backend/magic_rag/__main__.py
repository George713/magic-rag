import argparse
import json
import uvicorn
from .app import create_app, default_db_path, connect
from .ingest import ingest_sample
from .vectors import BgeEmbedder
from .corpus import import_corpus, LocalScryfallSource, ScryfallSource
from .evaluation import write_report
from pathlib import Path
import anyio
import httpx


async def benchmark_application(payload):
    # Use the same ASGI boundary as a server request, including AnyIO worker context.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://magic-rag.local", timeout=None) as client:
        response = await client.post("/api/benchmark", json=payload)
        if not response.is_success:
            raise ValueError(response.json().get("detail", "Benchmark request failed."))
        return response.json()

parser = argparse.ArgumentParser(description="Local Magic retrieval")
parser.add_argument("command", choices=["serve", "sample", "sample-vectors", "import", "benchmark"])
parser.add_argument("--port", type=int, default=8000)
parser.add_argument("--source", type=str, help="Existing Scryfall gzip JSONL export; otherwise discover and download current oracle_cards.")
parser.add_argument("--output", default="reports/retrieval-benchmark.json", help="Benchmark JSON output; sibling Markdown report is also written.")
parser.add_argument("--benchmark-suite", help="Optional reviewed benchmark-suite JSON; defaults to packaged twenty-question suite.")
parser.add_argument("--settings", help="Optional retrieval-settings JSON file for the benchmark.")
parser.add_argument("--cutoff", type=int, default=5, help="Record this ranking cutoff before evaluation.")
parser.add_argument("--no-warmup", action="store_true", help="Include initial model acquisition/loading in the first measured calls.")
args = parser.parse_args()
if args.command == "benchmark":
    try:
        payload = {"cutoff":args.cutoff, "warmup":not args.no_warmup}
        if args.benchmark_suite:
            payload["suite"] = json.loads(Path(args.benchmark_suite).read_text(encoding="utf-8-sig"))
        if args.settings:
            payload["settings"] = json.loads(Path(args.settings).read_text(encoding="utf-8-sig"))
        report = anyio.run(benchmark_application, payload)
        print(json.dumps({"outputs":write_report(report, args.output), "corpus":report["corpus"], "aggregates":report["aggregates"]}))
    except Exception as exc:
        parser.exit(1, f"Benchmark failed: {getattr(exc, 'detail', str(exc))}\n")
elif args.command == "import":
    try:
        result = import_corpus(lambda: connect(default_db_path()), LocalScryfallSource(args.source) if args.source else ScryfallSource(), BgeEmbedder())
        print(json.dumps(result))
    except Exception as exc:
        parser.exit(1, f"Corpus import failed; previous corpus preserved. {exc}\n")
elif args.command in ("sample", "sample-vectors"):
    print(json.dumps(ingest_sample(default_db_path(), embedder=BgeEmbedder() if args.command == "sample-vectors" else None)))
else:
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port)
