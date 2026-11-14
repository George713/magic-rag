from fastapi.testclient import TestClient
import pytest
import json

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from magic_rag.app import create_app
from magic_rag.ingest import ingest_sample
from magic_rag.providers import provider_from_env
from scripted_chat_model import ScriptedChatModel, searching
from test_streaming import send_message


def answered(client, question="Delver"):
    """Send one message in a new conversation; returns the conversation ID and the `done` event."""
    conversation_id = client.post("/api/conversations").json()["id"]
    return conversation_id, send_message(client, conversation_id, question)[-1]


def test_unconfigured_generation_preserves_retrieved_card_evidence(tmp_path):
    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path)) as client:
        status = client.get("/api/provider")
        assert status.status_code == 200
        assert status.json()["status"] == "unconfigured"
        trace = answered(client)[1]["trace"]
    assert trace["generation"]["status"] == "unconfigured"
    assert trace["selected_evidence"][0]["name"] == "Delver of Secrets // Insectile Aberration"


def test_cited_answer_receives_complete_selected_card_text(tmp_path):
    def answer(call):
        card = call.source["selected_evidence"][0]
        assert call.source["question"] == "Delver"
        assert "Flying" in card["text"]
        assert "look at the top card" in card["text"]
        return {"text": "Its transformed face has flying.", "citations": [card["card_id"]], "insufficient_evidence": False}

    model = ScriptedChatModel(script=searching(answer))
    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=model)) as client:
        trace = answered(client)[1]["trace"]
    answer = trace["generation"]
    assert answer["status"] == "completed"
    assert answer["text"] == "Its transformed face has flying."
    assert answer["citations"] == [{"card_id": "sample-delver", "name": "Delver of Secrets // Insectile Aberration"}]
    assert answer["insufficient_evidence"] is False
    assert len(model.calls) == 3  # Choose the search, stop searching, answer.


@pytest.mark.parametrize("result", [
    {"text": "Invented claim", "citations": ["invented-card"], "insufficient_evidence": False},
    {"text": "Uncited claim", "citations": [], "insufficient_evidence": False},
    {"text": "Malformed claim", "citations": [], "insufficient_evidence": "false"},
])
def test_invalid_provider_evidence_is_failed_without_losing_retrieval(tmp_path, result):
    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=searching(result)))) as client:
        trace = answered(client)[1]["trace"]
    assert trace["generation"]["status"] == "failed"
    assert "Invented" not in json.dumps(trace["generation"]["citations"])
    assert trace["selected_evidence"][0]["card_id"] == "sample-delver"


def test_no_evidence_is_explicit_without_an_answer_request(tmp_path):
    model = ScriptedChatModel(script=searching("Never requested."))
    with TestClient(create_app(tmp_path / "empty.db", chat_model=model)) as client:
        trace = answered(client, "unknown")[1]["trace"]
    assert trace["generation"]["status"] == "completed"
    assert trace["generation"]["insufficient_evidence"] is True
    assert trace["generation"]["citations"] == []
    assert "insufficient" in trace["generation"]["text"].lower()
    assert all(call.kwargs.get("tools") for call in model.calls)


def test_provider_failure_never_exposes_credentials_and_search_can_continue(tmp_path):
    model = ScriptedChatModel(script=searching(RuntimeError("secret-api-key-and-private-endpoint")))
    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=model)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        response = client.post(f"/api/conversations/{conversation_id}/messages", json={"question": "Delver"})
        assert json.loads(response.text.splitlines()[-1])["generation"]["status"] == "failed"
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
        conversation_id = client.post("/api/conversations").json()["id"]
        response = client.post(f"/api/conversations/{conversation_id}/messages", json={"question": "Delver"})
    assert json.loads(response.text.splitlines()[-1])["generation"]["status"] == "suitability_required"
    assert "server-secret" not in response.text
    assert "invalid.example" not in response.text


def test_model_receives_selected_text_and_the_conversation_session(tmp_path):
    def answer(call):
        assert call.session == conversation_id
        assert call.kwargs["response_format"] == {"type": "json_object"}
        assert call.source["question"] == "Delver"
        assert call.source["selected_evidence"][0]["card_id"] == "sample-delver"
        assert "look at the top card" in call.source["selected_evidence"][0]["text"]
        return {"text": "The evidence does not establish this interaction.", "citations": ["sample-delver"], "insufficient_evidence": True}

    path = tmp_path / "cards.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=searching(answer)))) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        answer = send_message(client, conversation_id, "Delver")[-1]["generation"]
    assert answer["status"] == "completed"
    assert answer["insufficient_evidence"] is True
    assert answer["citations"][0]["name"] == "Delver of Secrets // Insectile Aberration"


@pytest.mark.parametrize("finish_reason", ["length", None])
def test_truncated_model_answer_fails_without_losing_evidence(tmp_path, finish_reason):
    content = json.dumps({"text": "Its transformed face has flying.", "citations": ["sample-delver"]})
    path = tmp_path / "cards.db"
    ingest_sample(path)
    model = ScriptedChatModel(script=searching(AIMessage(content=content, response_metadata={"finish_reason": finish_reason})))
    with TestClient(create_app(path, chat_model=model)) as client:
        trace = answered(client)[1]["trace"]
    assert trace["generation"]["status"] == "failed"
    assert trace["selected_evidence"][0]["card_id"] == "sample-delver"


def test_configured_provider_uses_openai_compatible_model_with_go_client_headers(monkeypatch):
    monkeypatch.setenv("MAGIC_RAG_PROVIDER_URL", "https://provider.example/v1/chat/completions")
    monkeypatch.setenv("MAGIC_RAG_PROVIDER_MODEL", "configured-model")
    monkeypatch.setenv("MAGIC_RAG_PROVIDER_API_KEY", "server-key")
    monkeypatch.setenv("MAGIC_RAG_PROVIDER_SUITABILITY_CONFIRMED", "true")
    model = provider_from_env().chat_model
    assert isinstance(model, ChatOpenAI)
    assert model.openai_api_base == "https://provider.example/v1"
    assert model.model_name == "configured-model"
    assert model.default_headers["User-Agent"] == "magic-rag/0.1"
    assert "server-key" not in repr(model)


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
    path = tmp_path / "assets.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=searching(payload)))) as client:
        conversation_id, done = answered(client)
        trace = done["trace"]
        answer = trace["generation"]
        assert answer["status"] == "completed"
        assert answer["assets"][0]["card_id"] == "sample-delver"
        assert answer["assets"][0] == trace["selected_evidence"][0]
        assert answer["text"] == payload.get("text", "")
    with TestClient(create_app(path)) as restarted:
        saved = restarted.get(f"/api/conversations/{conversation_id}").json()
        assert saved["turns"][0]["trace"]["generation"] == answer


@pytest.mark.parametrize("payload", [
    {}, {"text": "   "}, {"assets": ["invented-card"]},
    {"assets": [{"card_id": "sample-delver", "url": "https://invented.example/card.png"}]},
    {"assets": ["sample-delver"], "image_url": "https://invented.example/card.png"},
    {"text": "An uncited claim", "assets": ["sample-delver"]},
])
def test_empty_or_untrusted_asset_answers_fail_without_losing_evidence(tmp_path, payload):
    path = tmp_path / "assets.db"
    ingest_sample(path)
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=searching(payload)))) as client:
        trace = answered(client)[1]["trace"]
        assert trace["generation"]["status"] == "failed"
        assert not trace["generation"].get("assets")
        assert trace["selected_evidence"][0]["card_id"] == "sample-delver"
