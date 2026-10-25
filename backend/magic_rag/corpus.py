"""Manual, validated corpus replacement; conversations never leave the database."""
import gzip
import hashlib
import json
import math
import os
import platform
from pathlib import Path
import tempfile
from time import perf_counter
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

from .reranking import card_document
from .vectors import prepare_vectors, write_vectors


class CorpusError(ValueError):
    pass


def source_url(value):
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    return value if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password else None


def source_images(record, faces):
    images = []
    # A printing either has one complete image or separate face images.
    for face in ([record] if record.get("image_uris") else faces):
        variants = face.get("image_uris") or {}
        url = source_url(variants.get("normal") or variants.get("large") or variants.get("png"))
        if url:
            images.append({"name":face.get("name", record["name"]), "url":url})
    return images


def normalize(record):
    card_id = record.get("oracle_id")
    if not isinstance(card_id, str) or not card_id:
        raise CorpusError("A record has no canonical oracle_id. Reversible cards without a root identity require explicit handling; printing IDs are not substituted.")
    name = record.get("name")
    faces = record.get("card_faces", [])
    if not isinstance(name, str) or not name.strip() or not isinstance(faces, list):
        raise CorpusError("Card name or face structure is invalid.")
    mana_value = record.get("cmc")
    if not isinstance(mana_value, (int, float)) or not math.isfinite(mana_value) or mana_value < 0:
        raise CorpusError(f"Invalid numeric mana value for {name}.")
    colors = record.get("colors")
    if colors is None:
        colors = sorted({color for face in faces for color in face.get("colors", [])})
    if not isinstance(colors, list) or any(color not in {"W", "U", "B", "R", "G"} for color in colors):
        raise CorpusError(f"Invalid card colors for {name}.")
    text_parts = []
    for face in ([record] + faces):
        # Keep canonical fields, never localized printed_name/printed_text.
        values = [face.get(field, "") for field in ("name", "mana_cost", "type_line", "oracle_text")]
        if "colors" in face:
            values.append("Colors: " + ", ".join(face["colors"]))
        values.extend(f"{field}: {face[field]}" for field in ("power", "toughness", "loyalty", "defense") if field in face)
        if any(not isinstance(value, str) for value in values):
            raise CorpusError(f"Invalid canonical text for {name}.")
        text_parts.append("\n".join(value for value in values if value))
    type_line = record.get("type_line") or " // ".join(face.get("type_line", "") for face in faces)
    if not type_line:
        raise CorpusError(f"Missing canonical card type for {name}.")
    return {"card_id":card_id, "name":name, "text":"\n\n".join(text_parts),
            "mana_cost":record.get("mana_cost") or " // ".join(face.get("mana_cost", "") for face in faces),
            "mana_value":float(mana_value), "colors":sorted(set(colors)), "type_line":type_line,
            "images":source_images(record, faces), "source_url":source_url(record.get("scryfall_uri"))}


class LocalScryfallSource:
    def __init__(self, path: Path):
        self.path = Path(path)

    def snapshot(self):
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        with gzip.open(self.path, "rt", encoding="utf-8") as source:
            records = [json.loads(line) for line in source if line.strip()]
        return {"id":f"scryfall-local:{digest}", "source":"Scryfall oracle_cards gzip JSONL",
                "sha256":digest, "source_file":self.path.name}, records


class ScryfallSource:
    def __init__(self, *, transport=None):
        self.transport = transport

    def snapshot(self):
        headers = {"User-Agent":"magic-rag/0.1", "Accept":"application/json"}
        with httpx.Client(headers=headers, timeout=120, follow_redirects=True, transport=self.transport) as client:
            response = client.get("https://api.scryfall.com/bulk-data")
            response.raise_for_status()
            metadata = next((item for item in response.json()["data"] if item.get("type") == "oracle_cards"), None)
            if not metadata or not metadata.get("jsonl_download_uri"):
                raise CorpusError("Scryfall oracle_cards metadata has no jsonl_download_uri. Verify the current export contract.")
            uri = metadata["jsonl_download_uri"]
            parsed = urlparse(uri)
            if parsed.scheme != "https" or parsed.hostname != "data.scryfall.io" or parsed.username or parsed.password:
                raise CorpusError("Scryfall export URI is not an expected HTTPS data.scryfall.io download.")
            with tempfile.TemporaryDirectory(prefix="magic-rag-import-") as directory:
                path = Path(directory) / "oracle-cards.jsonl.gz"
                with client.stream("GET", uri) as stream, path.open("wb") as output:
                    stream.raise_for_status()
                    for chunk in stream.iter_raw():
                        output.write(chunk)
                if path.stat().st_size != metadata.get("compressed_size"):
                    raise CorpusError("Downloaded Scryfall compressed_size differs from metadata; previous corpus was not changed.")
                provenance, records = LocalScryfallSource(path).snapshot()
            provenance.update(id=f'scryfall:{metadata["updated_at"]}:{provenance["sha256"]}',
                              download_uri=uri, updated_at=metadata["updated_at"], bulk_id=metadata["id"])
            return provenance, records


def import_corpus(connection, source, embedder):
    start = perf_counter()
    metadata, records = source.snapshot()
    if not metadata.get("id"):
        raise CorpusError("Corpus snapshot must have a stable identity.")
    cards = {}
    count = 0
    for record in records:
        count += 1
        card = normalize(record)
        previous = cards.get(card["card_id"])
        canonical = lambda item: {key:value for key,value in item.items() if key not in {"images", "source_url"}}
        if previous is not None and canonical(previous) != canonical(card):
            raise CorpusError(f'Conflicting canonical information for {card["card_id"]}.')
        if previous is None:
            cards[card["card_id"]] = card
    if not cards:
        raise CorpusError("Export contains no distinct cards; refusing to replace the working corpus.")
    documents = [(card["card_id"], card_document(card)) for card in cards.values()]
    config, vectors = prepare_vectors(documents, embedder)
    metadata = {**metadata, "input_records":count, "card_count":len(cards), "embedding":config,
                "execution":{"platform":platform.platform(), "processor":platform.processor(), "device":getattr(embedder,"device","injected"),
                             "embedding_batch_size":os.environ.get("MAGIC_RAG_EMBEDDING_BATCH_SIZE","32"), "omp_threads":os.environ.get("OMP_NUM_THREADS","runtime default")}}
    # Normalization and every embedding complete before the activation transaction.
    # SQLite rolls back text, both indexes, and identity together on any failure.
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM card_fts")
        db.execute("DELETE FROM cards")
        db.execute("DELETE FROM card_images")
        db.execute("DELETE FROM corpus")
        db.executemany("INSERT INTO cards VALUES (?, ?, ?, ?, ?, ?, ?)", [
            (card["card_id"],card["name"],card["text"],card["mana_cost"],card["mana_value"],json.dumps(card["colors"]),card["type_line"]) for card in cards.values()])
        db.executemany("INSERT INTO card_images VALUES (?, ?, ?)", [
            (card["card_id"], json.dumps(card["images"]), card["source_url"]) for card in cards.values()])
        db.executemany("INSERT INTO card_fts VALUES (?, ?)", documents)
        write_vectors(db, config, vectors)
        for table in ("cards", "card_fts", "card_vectors"):
            if db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] != len(cards):
                raise CorpusError("Replacement index validation failed; previous corpus preserved.")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise CorpusError("Replacement database integrity check failed.")
        db.execute("INSERT INTO corpus VALUES (?, ?)", (metadata["id"],json.dumps(metadata)))
    return {"status":"activated", "corpus_id":metadata["id"], "card_count":len(cards), "elapsed_ms":(perf_counter()-start)*1000}


def register_corpus(app, connection, embedder, source=None):
    @app.get("/api/corpus")
    def active_corpus():
        with connection() as db:
            row = db.execute("SELECT id,metadata FROM corpus LIMIT 1").fetchone()
            return {"id":row[0],"metadata":json.loads(row[1])} if row else None

    @app.post("/api/corpus/import")
    def refresh_corpus():
        try:
            return import_corpus(connection, source or ScryfallSource(), embedder)
        except Exception as exc:
            raise HTTPException(422, f"Corpus import failed; previous corpus preserved. {exc}") from exc
