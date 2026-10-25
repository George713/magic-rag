from fastapi.testclient import TestClient
import pytest
import httpx
import json

from magic_rag.app import create_app
from magic_rag.ingest import ingest_sample
from magic_rag.providers import ChatCompletionsProvider, ProviderConfig


def test_unconfigured_generation_preserves_retrieved_card_evidence(tmp_path):
    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path)) as client:
        status = client.get("/api/provider")
        assert status.status_code == 200
        assert status.json()["status"] == "unconfigured"
        trace = client.post("/api/search", json={"question": "Delver", "generate_answer": True}).json()
    assert trace["generation"]["status"] == "unconfigured"
    assert trace["selected_evidence"][0]["name"] == "Delver of Secrets // Insectile Aberration"


def test_cited_answer_receives_complete_selected_card_text(tmp_path):
    class EvidenceProvider:
        def answer(self, question, evidence, session_id, *, context=None):
            card = evidence[0]
            assert question == "Delver"
            assert "Flying" in card["text"]
            assert "look at the top card" in card["text"]
            return {"text": "Its transformed face has flying.", "citations": [card["card_id"]], "insufficient_evidence": False}

    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, provider=EvidenceProvider())) as client:
        trace = client.post("/api/search", json={"question": "Delver", "generate_answer": True}).json()
    answer = trace["generation"]
    assert answer["status"] == "completed"
    assert answer["text"] == "Its transformed face has flying."
    assert answer["citations"] == [{"card_id": "sample-delver", "name": "Delver of Secrets // Insectile Aberration"}]
    assert answer["insufficient_evidence"] is False


@pytest.mark.parametrize("result", [
    {"text": "Invented claim", "citations": ["invented-card"], "insufficient_evidence": False},
    {"text": "Uncited claim", "citations": [], "insufficient_evidence": False},
    {"text": "Malformed claim", "citations": [], "insufficient_evidence": "false"},
])
def test_invalid_provider_evidence_is_failed_without_losing_retrieval(tmp_path, result):
    class InvalidProvider:
        def answer(self, question, evidence, session_id, *, context=None):
            return result

    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, provider=InvalidProvider())) as client:
        trace = client.post("/api/search", json={"question": "Delver", "generate_answer": True}).json()
    assert trace["generation"]["status"] == "failed"
    assert "text" not in trace["generation"]
    assert trace["selected_evidence"][0]["card_id"] == "sample-delver"


def test_no_evidence_is_explicit_without_contacting_provider(tmp_path):
    class UnneededProvider:
        def answer(self, *args, context=None):
            raise AssertionError("An empty evidence set must not be sent for generation")

    with TestClient(create_app(tmp_path / "empty.db", provider=UnneededProvider())) as client:
        trace = client.post("/api/search", json={"question": "unknown", "generate_answer": True}).json()
    assert trace["generation"]["status"] == "completed"
    assert trace["generation"]["insufficient_evidence"] is True
    assert trace["generation"]["citations"] == []
    assert "insufficient" in trace["generation"]["text"].lower()


def test_provider_failure_never_exposes_credentials_and_search_can_continue(tmp_path):
    class FailedProvider:
        def answer(self, *args, context=None):
            raise RuntimeError("secret-api-key-and-private-endpoint")

    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, provider=FailedProvider())) as client:
        response = client.post("/api/search", json={"question": "Delver", "generate_answer": True})
        assert response.json()["generation"]["status"] == "failed"
        assert "secret-api-key" not in response.text
        assert client.post("/api/search", json={"question": "Lightning"}).json()["selected_evidence"]


def test_unverified_provider_configuration_is_visible_and_makes_no_call(tmp_path, monkeypatch):
    monkeypatch.setenv("MAGIC_RAG_PROVIDER_URL", "https://invalid.example/chat/completions")
    monkeypatch.setenv("MAGIC_RAG_PROVIDER_MODEL", "unverified-model")
    monkeypatch.setenv("MAGIC_RAG_PROVIDER_API_KEY", "server-secret")
    monkeypatch.delenv("MAGIC_RAG_PROVIDER_SUITABILITY_CONFIRMED", raising=False)
    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path)) as client:
        status = client.get("/api/provider").json()
        assert status["status"] == "suitability_required"
        response = client.post("/api/search", json={"question": "Delver", "generate_answer": True})
    assert response.json()["generation"]["status"] == "suitability_required"
    assert "server-secret" not in response.text
    assert "invalid.example" not in response.text


def test_configured_transport_sends_selected_text_and_validates_answer(tmp_path):
    def remote(request):
        assert request.headers["Authorization"] == "Bearer server-only-key"
        assert request.headers["User-Agent"] == "magic-rag/0.1"
        assert request.headers["x-opencode-session"]
        body = json.loads(request.content)
        source = json.loads(body["messages"][1]["content"])
        assert source["question"] == "Delver"
        assert source["selected_evidence"][0]["card_id"] == "sample-delver"
        assert "Flying" in source["selected_evidence"][0]["text"]
        assert "look at the top card" in source["selected_evidence"][0]["text"]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "text": "The evidence does not establish this interaction.", "citations": ["sample-delver"], "insufficient_evidence": True})}}]})

    path = tmp_path / "cards.db"
    ingest_sample(path)
    adapter = ChatCompletionsProvider(ProviderConfig("https://provider.example/chat/completions", "test-model", "server-only-key", True), transport=httpx.MockTransport(remote))
    with TestClient(create_app(path, provider=adapter)) as client:
        response = client.post("/api/search", json={"question": "Delver", "generate_answer": True})
    answer = response.json()["generation"]
    assert answer["status"] == "completed"
    assert answer["insufficient_evidence"] is True
    assert answer["citations"][0]["name"] == "Delver of Secrets // Insectile Aberration"
    assert "server-only-key" not in response.text


def test_provider_can_be_configured_without_selecting_a_default_service(tmp_path, monkeypatch):
    monkeypatch.setenv("MAGIC_RAG_PROVIDER_URL", "https://provider.example/chat/completions")
    monkeypatch.setenv("MAGIC_RAG_PROVIDER_MODEL", "configured-model")
    monkeypatch.setenv("MAGIC_RAG_PROVIDER_API_KEY", "server-key")
    monkeypatch.setenv("MAGIC_RAG_PROVIDER_SUITABILITY_CONFIRMED", "true")
    with TestClient(create_app(tmp_path / "empty.db")) as client:
        response = client.get("/api/provider")
    assert response.json()["status"] == "ready"
    assert "server-key" not in response.text
    assert "provider.example" not in response.text

@pytest.mark.parametrize("payload", [
    {"assets": ["sample-delver"]},
    {"text": "Its transformed face has flying.", "citations": ["sample-delver"], "insufficient_evidence": False, "assets": ["sample-delver"]},
])
def test_selected_card_assets_complete_and_survive_restart(tmp_path, payload):
    class AssetProvider:
        def answer(self, *args, **kwargs):
            return payload

    path = tmp_path / "assets.db"
    ingest_sample(path)
    with TestClient(create_app(path, provider=AssetProvider())) as client:
        conversation = client.post("/api/conversations").json()
        trace = client.post("/api/search", json={"question": "Delver", "generate_answer": True, "conversation_id": conversation["id"]}).json()
        answer = trace["generation"]
        assert answer["status"] == "completed"
        assert answer["assets"][0]["card_id"] == "sample-delver"
        assert answer["assets"][0] == trace["selected_evidence"][0]
        assert answer["text"] == payload.get("text", "")
    with TestClient(create_app(path)) as restarted:
        saved = restarted.get(f"/api/conversations/{conversation['id']}").json()
        assert saved["turns"][0]["trace"]["generation"] == answer


@pytest.mark.parametrize("payload", [
    {}, {"text": "   "}, {"assets": ["invented-card"]},
    {"assets": [{"card_id": "sample-delver", "url": "https://invented.example/card.png"}]},
    {"assets": ["sample-delver"], "image_url": "https://invented.example/card.png"},
    {"text": "An uncited claim", "assets": ["sample-delver"]},
])
def test_empty_or_untrusted_asset_answers_fail_without_losing_evidence(tmp_path, payload):
    class InvalidAssetProvider:
        def answer(self, *args, **kwargs):
            return payload

    path = tmp_path / "assets.db"
    ingest_sample(path)
    with TestClient(create_app(path, provider=InvalidAssetProvider())) as client:
        trace = client.post("/api/search", json={"question": "Delver", "generate_answer": True}).json()
        assert trace["generation"]["status"] == "failed"
        assert not trace["generation"].get("assets")
        assert trace["selected_evidence"][0]["card_id"] == "sample-delver"
