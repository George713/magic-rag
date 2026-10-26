"""A deliberately small controlled fixture, not a current Scryfall export."""
import json
from pathlib import Path
from .app import connect
from .vectors import Embedder, store_vectors


SAMPLE = [
    {"card_id": "sample-lightning-bolt", "name": "Lightning Bolt", "mana_cost": "{R}", "mana_value": 1,
     "colors": ["R"], "type_line": "Instant", "text": "Lightning Bolt deals 3 damage to any target."},
    {"card_id": "sample-delver", "name": "Delver of Secrets // Insectile Aberration", "mana_cost": "{U}",
     "mana_value": 1, "colors": ["U"], "type_line": "Creature — Human Wizard // Creature — Human Insect",
     "text": "Delver of Secrets\nAt the beginning of your upkeep, look at the top card of your library. You may reveal that card. If an instant or sorcery card is revealed this way, transform Delver of Secrets.\n\nInsectile Aberration\nFlying"},
    {"card_id": "sample-sol-ring", "name": "Sol Ring", "mana_cost": "{1}", "mana_value": 1,
     "colors": [], "type_line": "Artifact", "text": "{T}: Add {C}{C}."},
]


def ingest_sample(path: Path, *, embedder: Embedder | None = None):
    # Repeated printing deliberately shares the canonical identity.
    printings = SAMPLE + [SAMPLE[1].copy()]
    with connect(path) as db:
        documents = []
        db.execute("DELETE FROM card_fts")
        db.execute("DELETE FROM cards")
        db.execute("DELETE FROM corpus")
        for card in {card["card_id"]: card for card in printings}.values():
            db.execute("INSERT INTO cards VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (card["card_id"], card["name"], card["text"], card["mana_cost"],
                        card["mana_value"], json.dumps(card["colors"]), card["type_line"]))
            document = "\n".join([card["name"], card["mana_cost"], card["type_line"], " ".join(card["colors"]), card["text"]])
            db.execute("INSERT INTO card_fts VALUES (?, ?)", (card["card_id"], document))
            documents.append((card["card_id"], document))
        if embedder:
            store_vectors(db, documents, embedder)
        else:
            db.execute("DROP TABLE IF EXISTS card_vectors")
            db.execute("DELETE FROM embedding_config")
        db.execute("INSERT INTO corpus VALUES (?, ?)", ("controlled-sample-v1", json.dumps({"source": "controlled fixture", "card_count": 3})))
    return {"corpus_id": "controlled-sample-v1", "card_count": 3}
