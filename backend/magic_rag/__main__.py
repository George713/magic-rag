import argparse
import json
import uvicorn
from .app import create_app, default_db_path, connect
from .ingest import ingest_sample
from .vectors import BgeEmbedder
from .corpus import import_corpus, LocalScryfallSource, ScryfallSource

parser = argparse.ArgumentParser(description="Local Magic retrieval")
parser.add_argument("command", choices=["serve", "sample", "sample-vectors", "import"])
parser.add_argument("--port", type=int, default=8000)
parser.add_argument("--source", type=str, help="Existing Scryfall gzip JSONL export; otherwise discover and download current oracle_cards.")
args = parser.parse_args()
if args.command == "import":
    try:
        result = import_corpus(lambda: connect(default_db_path()), LocalScryfallSource(args.source) if args.source else ScryfallSource(), BgeEmbedder())
        print(json.dumps(result))
    except Exception as exc:
        parser.exit(1, f"Corpus import failed; previous corpus preserved. {exc}\n")
elif args.command in ("sample", "sample-vectors"):
    print(json.dumps(ingest_sample(default_db_path(), embedder=BgeEmbedder() if args.command == "sample-vectors" else None)))
else:
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port)
