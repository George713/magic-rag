"""Two red artifact-sacrifice creatures with topic-controlled embedding and reranking, for follow-up checks."""
from magic_rag.app import connect
from magic_rag.vectors import store_vectors


INITIAL = "Find artifact-sacrifice creatures"
FOLLOWUP = "Any cheaper ones?"
FOLLOWUP_SEARCH = "Atog artifact sacrifice cheaper creatures"  # The model-written search for FOLLOWUP.
ATOG = "3095f2cf-05c3-4381-929f-c526b6fc30a7"
ENGINEER = "c1d6cce8-085f-42cb-8b0c-b6fbbf88b16a"


class TopicEmbedder:
    config = {"model": "topic-test-embedding", "revision": "1", "dimensions": 2}

    def document(self, text):
        return [1.0, 0.0] if text.startswith("Atog") else [0.0, 1.0]

    def query(self, text):
        return [1.0, 0.0] if text.startswith("Atog") else [0.0, 1.0]


class TopicReranker:
    config = {"model": "topic-test-reranker", "revision": "1"}

    def score(self, query, documents):
        return [9.0 if text.startswith("Atog") == query.startswith("Atog") else 1.0 for text in documents]


def seed_artifact_cards(path):
    cards = [
        (ATOG, "Atog", "Sacrifice an artifact: This creature gets +2/+2 until end of turn.", "{1}{R}", 2, '["R"]', "Creature — Atog"),
        (ENGINEER, "Goblin Engineer", "When this creature enters, you may search your library for an artifact card, put it into your graveyard, then shuffle.\n{R}, {T}, Sacrifice an artifact: Return target artifact card with mana value 3 or less from your graveyard to the battlefield.", "{1}{R}", 2, '["R"]', "Creature — Goblin Artificer"),
    ]
    with connect(path) as db:
        for card in cards:
            db.execute("INSERT INTO cards VALUES (?, ?, ?, ?, ?, ?, ?)", card)
            db.execute("INSERT INTO card_fts VALUES (?, ?)", (card[0], f"{card[1]} {card[2]} {card[6]}"))
        db.execute("INSERT INTO corpus VALUES ('topic-fixture', '{}')")
        store_vectors(db, [(card[0], f"{card[1]} {card[2]}") for card in cards], TopicEmbedder())
