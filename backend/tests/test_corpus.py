from fastapi.testclient import TestClient
from magic_rag.app import create_app
from test_vectors import ControlledEmbedder
import sqlite3
import gzip
import json
import httpx
from magic_rag.corpus import ScryfallSource


class FixtureSource:
    def snapshot(self):
        card = {"oracle_id":"canonical-one", "id":"printing-one", "name":"Twin Source", "cmc":1.5,
                "lang":"ja", "card_faces":[
                  {"name":"Front", "mana_cost":"{U}", "type_line":"Creature — Wizard", "colors":["U"], "oracle_text":"Draw a card."},
                  {"name":"Back", "mana_cost":"", "type_line":"Creature — Bird", "colors":["U"], "oracle_text":"Flying. Final ability."}]}
        return {"id":"snapshot-one", "source":"controlled export"}, [card, {**card,"id":"printing-two"}]


def test_import_collapses_printings_retains_all_faces_and_canonical_fields(tmp_path):
    with TestClient(create_app(tmp_path / "cards.db", embedder=ControlledEmbedder(), corpus_source=FixtureSource())) as client:
        response = client.post("/api/corpus/import")
        assert response.status_code == 200
        assert response.json()["card_count"] == 1
        trace = client.post("/api/search", json={"question":"Final ability"}).json()
        card = trace["selected_evidence"][0]
        assert card["card_id"] == "canonical-one"
        assert card["mana_value"] == 1.5
        assert card["colors"] == ["U"]
        assert "Draw a card." in card["text"]
        assert "Final ability." in card["text"]
        assert "Back" in card["text"]
        assert trace["corpus"]["id"] == "snapshot-one"
        assert client.get("/api/corpus").json()["metadata"]["embedding"] == ControlledEmbedder.config


def test_successful_refresh_and_later_failure_preserve_active_search_and_historical_evidence(tmp_path):
    source = FixtureSource()
    path = tmp_path / "cards.db"
    with TestClient(create_app(path, embedder=ControlledEmbedder(), corpus_source=source)) as client:
        assert client.post("/api/corpus/import").status_code == 200
        conversation_id = client.post("/api/conversations").json()["id"]
        original = client.post("/api/search", json={"question":"Final ability", "conversation_id":conversation_id}).json()
        metadata, records = source.snapshot()
        changed = [{**records[0], "name":"Replacement Source"}]
        source.snapshot = lambda: ({**metadata,"id":"snapshot-two"},changed)
        assert client.post("/api/corpus/import").json()["corpus_id"] == "snapshot-two"
        assert client.post("/api/search", json={"question":"Replacement"}).json()["selected_evidence"][0]["name"] == "Replacement Source"
        def fail():
            raise RuntimeError("Controlled download failure")
        source.snapshot = fail
        response = client.post("/api/corpus/import")
        assert response.status_code == 422
        assert "previous corpus preserved" in response.json()["detail"]
        assert client.get("/api/corpus").json()["id"] == "snapshot-two"
        assert client.post("/api/search", json={"question":"Replacement", "mode":"vector"}).status_code == 200
        assert client.get(f"/api/conversations/{conversation_id}").json()["turns"][0]["trace"] == original


def test_failed_embedding_or_missing_identity_never_activates_replacement(tmp_path):
    path = tmp_path / "cards.db"
    source = FixtureSource()
    model = ControlledEmbedder()
    with TestClient(create_app(path, embedder=model, corpus_source=source)) as client:
        assert client.post("/api/corpus/import").status_code == 200
        def fail_document(text):
            raise ValueError("Controlled embedding failure")
        model.document = fail_document
        assert client.post("/api/corpus/import").status_code == 422
        assert client.get("/api/corpus").json()["id"] == "snapshot-one"
        metadata, records = source.snapshot()
        source.snapshot = lambda: (metadata,[{**records[0], "oracle_id":None}])
        response = client.post("/api/corpus/import")
        assert "oracle_id" in response.json()["detail"]
        assert client.post("/api/search", json={"question":"Final ability"}).json()["selected_evidence"][0]["card_id"] == "canonical-one"


def test_long_multiface_evidence_reaches_both_model_boundaries_and_remains_readable(tmp_path):
    source = FixtureSource()
    metadata, records = source.snapshot()
    card = records[0]
    card["card_faces"][0]["oracle_text"] = "Ability " * 800 + " FIRST FACE END."
    source.snapshot = lambda: (metadata,[card])
    class CompleteEmbedder(ControlledEmbedder):
        def document(self, text):
            assert "FIRST FACE END." in text and "Final ability." in text
            return [1.,0.,0.]
    class CompleteReranker:
        config = {"model":"controlled","revision":"windows"}
        def score(self, query, documents):
            assert "FIRST FACE END." in documents[0] and "Final ability." in documents[0]
            return [1.]
    with TestClient(create_app(tmp_path / "cards.db",embedder=CompleteEmbedder(),reranker=CompleteReranker(),corpus_source=source)) as client:
        assert client.post("/api/corpus/import").status_code == 200
        trace = client.post("/api/search",json={"question":"Final ability","mode":"hybrid_rerank"}).json()
        assert "FIRST FACE END." in trace["selected_evidence"][0]["text"]
        assert "Final ability." in trace["selected_evidence"][0]["text"]


def test_database_failure_at_activation_rolls_back_both_indexes_and_corpus_identity(tmp_path):
    path = tmp_path / "cards.db"
    source = FixtureSource()
    with TestClient(create_app(path,embedder=ControlledEmbedder(),corpus_source=source)) as client:
        assert client.post("/api/corpus/import").status_code == 200
        before = client.post("/api/search",json={"question":"Final ability","mode":"hybrid"}).json()
        # Inject a real SQLite write failure at the storage boundary. Observe only
        # through the API: the trigger fires after replacement tables are written.
        with sqlite3.connect(path) as database:
            database.execute("CREATE TRIGGER reject_activation BEFORE INSERT ON corpus BEGIN SELECT RAISE(ABORT, 'controlled activation failure'); END")
        metadata, records = source.snapshot()
        source.snapshot = lambda: ({**metadata,"id":"must-not-activate"},[{**records[0],"name":"Replacement Source"}])
        response = client.post("/api/corpus/import")
        assert response.status_code == 422
        assert "controlled activation failure" in response.json()["detail"]
        after = client.post("/api/search",json={"question":"Final ability","mode":"hybrid"}).json()
        assert after["corpus"] == before["corpus"]
        assert after["stages"] == before["stages"]


def test_download_uses_current_gzip_jsonl_contract_and_rejects_incomplete_export(tmp_path):
    _, records = FixtureSource().snapshot()
    payload = gzip.compress("\n".join(json.dumps(card) for card in records).encode())
    state = {"size":len(payload)}
    def remote(request):
        assert request.headers["User-Agent"] == "magic-rag/0.1"
        assert request.headers["Accept"] == "application/json"
        if request.url.host == "api.scryfall.com":
            return httpx.Response(200,json={"data":[{"id":"bulk-id","type":"oracle_cards","updated_at":"2026-10-25T00:00:00Z",
                "jsonl_download_uri":"https://data.scryfall.io/oracle.jsonl.gz","compressed_size":state["size"]}]})
        return httpx.Response(200,stream=httpx.ByteStream(payload),headers={"content-type":"application/gzip"})
    source = ScryfallSource(transport=httpx.MockTransport(remote))
    with TestClient(create_app(tmp_path / "cards.db",embedder=ControlledEmbedder(),corpus_source=source)) as client:
        assert client.post("/api/corpus/import").status_code == 200
        before = client.get("/api/corpus").json()
        assert before["metadata"]["bulk_id"] == "bulk-id"
        assert before["metadata"]["updated_at"] == "2026-10-25T00:00:00Z"
        state["size"] += 1
        response = client.post("/api/corpus/import")
        assert response.status_code == 422
        assert "compressed_size" in response.json()["detail"]
        assert client.get("/api/corpus").json() == before


def test_imported_face_properties_filter_all_four_modes_before_selection(tmp_path):
    class SingleReranker:
        config = {"model":"controlled","revision":"1"}
        def score(self, query, documents):
            return [1.] * len(documents)
    with TestClient(create_app(tmp_path / "cards.db",embedder=ControlledEmbedder(),reranker=SingleReranker(),corpus_source=FixtureSource())) as client:
        assert client.post("/api/corpus/import").status_code == 200
        for mode in ("keyword","vector","hybrid","hybrid_rerank"):
            request = {"question":"Final ability","mode":mode,
                       "filters":{"colors":["U"],"card_types":["Creature"],"mana_value_min":1.5,"mana_value_max":1.5}}
            assert client.post("/api/search",json=request).json()["selected_evidence"][0]["card_id"] == "canonical-one"
            request["filters"]["colors"] = ["R"]
            assert client.post("/api/search",json=request).json()["selected_evidence"] == []
