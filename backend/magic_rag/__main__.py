import argparse
import json
import uvicorn
from .app import create_app, default_db_path
from .ingest import ingest_sample

parser = argparse.ArgumentParser(description="Local Magic retrieval")
parser.add_argument("command", choices=["serve", "sample"])
parser.add_argument("--port", type=int, default=8000)
args = parser.parse_args()
if args.command == "sample":
    print(json.dumps(ingest_sample(default_db_path())))
else:
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port)
