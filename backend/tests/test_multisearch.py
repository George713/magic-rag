"""Up to three searches per message: behavior through the streamed-message endpoint."""
import json

from fastapi.testclient import TestClient

from magic_rag.app import create_app
from magic_rag.ingest import ingest_sample
from scripted_chat_model import DONE_SEARCHING, ScriptedChatModel, offers_tools, search_call
from test_streaming import send_message

BOLT, DELVER, SOL_RING = "sample-lightning-bolt", "sample-delver", "sample-sol-ring"


def searches_of(events):
    return [event for event in events if event["event"] == "search"]


def test_two_searches_stream_in_order_and_the_answer_cites_cards_from_either(tmp_path):
    path = tmp_path / "cards.db"
    ingest_sample(path)
    answer = {"text": "Bolt deals 3; Delver flips.", "citations": [BOLT, DELVER], "insufficient_evidence": False}
    model = ScriptedChatModel(script=[search_call("Lightning Bolt"), search_call("Delver of Secrets"), "Done searching.", answer])
    with TestClient(create_app(path, chat_model=model)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = send_message(client, conversation_id, "compare Lightning Bolt and Delver")
        assert [event["event"] for event in events[:3]] == ["start", "search", "search"]
        assert [(event["index"], event["query"]) for event in searches_of(events)] == [(0, "Lightning Bolt"), (1, "Delver of Secrets")]
        done = events[-1]
        assert done["generation"]["status"] == "completed"
        assert [citation["card_id"] for citation in done["generation"]["citations"]] == [BOLT, DELVER]
        assert {card["card_id"] for card in done["trace"]["selected_evidence"]} == {BOLT, DELVER}
        assert [search["query"] for search in done["trace"]["searches"]] == ["Lightning Bolt", "Delver of Secrets"]
        # The second tool-offering call sees the first search's results.
        second = model.calls[1]
        assert offers_tools(second)
        assert [json.loads(m.content)[0]["card_id"] for m in second.messages if m.type == "tool"] == [BOLT]
        turn = client.get(f"/api/conversations/{conversation_id}").json()["turns"][0]
        assert turn["state"] == "completed"
        assert [search["query"] for search in turn["trace"]["searches"]] == ["Lightning Bolt", "Delver of Secrets"]


def test_a_model_that_keeps_searching_is_stopped_after_three_searches_and_must_answer(tmp_path):
    path = tmp_path / "cards.db"
    ingest_sample(path)
    queries = iter(["Lightning Bolt", "Delver", "Sol Ring", "Fourth search", "Fifth search", "Sixth search"])

    def model(call):
        if offers_tools(call):
            return search_call(next(queries), next(queries))  # Two calls per turn: the fourth exceeds the limit.
        return {"text": "Bolt, Delver, and Sol Ring.", "citations": [BOLT, DELVER, SOL_RING], "insufficient_evidence": False}

    scripted = ScriptedChatModel(script=model)
    with TestClient(create_app(path, chat_model=scripted)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = send_message(client, conversation_id, "show me three cards")
        assert [event["query"] for event in searches_of(events)] == ["Lightning Bolt", "Delver", "Sol Ring"]
        done = events[-1]
        assert done["generation"]["status"] == "completed"
        assert [search["query"] for search in done["trace"]["searches"]] == ["Lightning Bolt", "Delver", "Sol Ring"]
        assert "Fourth search" not in json.dumps(done["trace"])
        assert [offers_tools(call) for call in scripted.calls] == [True, True, False]
        assert scripted.calls[-1].source["search_queries"] == ["Lightning Bolt", "Delver", "Sol Ring"]

        # One call per model turn, forever: the third search is the last, and the answer call offers no tool.
        repeating = ScriptedChatModel(script=lambda call: search_call("Delver") if offers_tools(call) else
                                      {"text": "Delver flips.", "citations": [DELVER], "insufficient_evidence": False})
    with TestClient(create_app(path, chat_model=repeating)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = send_message(client, conversation_id, "Delver again and again")
        assert len(searches_of(events)) == 3
        assert events[-1]["generation"]["status"] == "completed"
        assert [offers_tools(call) for call in repeating.calls] == [True, True, True, False]
        assert [card["card_id"] for card in events[-1]["trace"]["selected_evidence"]] == [DELVER]


def seed_pairs(path, *topics):
    """Two keyword-searchable cards per topic word, e.g. "Alpha Wurm" and "Alpha Drake"."""
    from magic_rag.app import connect

    with connect(path) as db:
        for topic in topics:
            for kind in ("Wurm", "Drake"):
                card_id, name = f"{topic.lower()}-{kind.lower()}", f"{topic} {kind}"
                text = f"{topic} {kind} gets +1/+1."
                db.execute("INSERT INTO cards VALUES (?, ?, ?, ?, ?, ?, ?)", (card_id, name, text, "{G}", 1, '["G"]', "Creature"))
                db.execute("INSERT INTO card_fts VALUES (?, ?)", (card_id, f"{name} {text} Creature"))


def test_evidence_is_capped_at_twice_the_per_search_size_keeping_each_searchs_best_cards(tmp_path):
    path = tmp_path / "cards.db"
    ingest_sample(path)
    seed_pairs(path, "Alpha", "Beta", "Gamma")
    every_card = [f"{topic}-{kind}" for topic in ("alpha", "beta", "gamma") for kind in ("wurm", "drake")]
    answer = {"text": "All six creatures.", "citations": every_card, "insufficient_evidence": False}
    model = ScriptedChatModel(script=[search_call("Alpha", "Beta", "Gamma"), answer])
    with TestClient(create_app(path, chat_model=model)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        settings = {"evidence_limit": 2}
        events = send_message(client, conversation_id, "the alpha, beta and gamma creatures", settings=settings)
        found = [[card["card_id"] for card in event["search"]["selected_evidence"]] for event in searches_of(events)]
        assert [len(cards) for cards in found] == [2, 2, 2]
        evidence = [card["card_id"] for card in events[-1]["trace"]["selected_evidence"]]
        # Total cap 4 = 2 x evidence limit: every search's best card first, then second-best in search order.
        assert evidence == [found[0][0], found[1][0], found[2][0], found[0][1]]
        # Each search event carries the combined evidence so far, so the chat shows it live.
        live = [[card["card_id"] for card in event["selected_evidence"]] for event in searches_of(events)]
        assert live == [found[0], [found[0][0], found[1][0], found[0][1], found[1][1]], evidence]
        assert [card["card_id"] for card in model.calls[-1].source["selected_evidence"]] == evidence
        assert events[-1]["generation"]["status"] == "failed"  # Two citations are beyond the cap.
        saved = client.get(f"/api/conversations/{conversation_id}").json()["turns"][0]["trace"]
        assert [card["card_id"] for card in saved["selected_evidence"]] == evidence


def test_long_card_text_arrives_complete_in_the_tool_results_the_model_sees_and_in_the_evidence(tmp_path):
    from magic_rag.app import connect

    path = tmp_path / "cards.db"
    ingest_sample(path)
    long_text = "Flying\n" + "\n".join(f"Ability {index}: draw a card." for index in range(2000)) + "\nFinal ability: you win the game."
    with connect(path) as db:
        db.execute("UPDATE cards SET text = ? WHERE card_id = ?", (long_text, DELVER))
    answer = {"text": "Delver and Bolt.", "citations": [DELVER, BOLT], "insufficient_evidence": False}
    model = ScriptedChatModel(script=[search_call("Delver"), search_call("Lightning Bolt"), "Done.", answer])
    with TestClient(create_app(path, chat_model=model)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = send_message(client, conversation_id, "the long card and Lightning Bolt")
        assert events[-1]["generation"]["status"] == "completed"
        tool_results = [json.loads(m.content) for m in model.calls[2].messages if m.type == "tool"]
        assert [[card["card_id"] for card in result] for result in tool_results] == [[DELVER], [BOLT]]
        assert tool_results[0][0]["text"] == long_text
        assert model.calls[-1].source["selected_evidence"][0]["text"] == long_text
        assert events[-1]["trace"]["selected_evidence"][0]["text"] == long_text


def test_citations_and_assets_must_come_from_the_combined_evidence(tmp_path):
    path = tmp_path / "cards.db"
    ingest_sample(path)
    cases = {
        "cites either search": ({"text": "Bolt and Delver.", "citations": [BOLT, DELVER], "insufficient_evidence": False}, "completed"),
        "assets from either search": ({"citations": [], "assets": [DELVER, BOLT], "insufficient_evidence": False}, "completed"),
        "cites an unsearched card": ({"text": "Sol Ring.", "citations": [SOL_RING], "insufficient_evidence": False}, "failed"),
        "asset of an unsearched card": ({"citations": [], "assets": [BOLT, SOL_RING], "insufficient_evidence": False}, "failed"),
        "text without citations": ({"text": "Bolt deals 3.", "citations": [], "insufficient_evidence": False}, "failed"),
    }
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=lambda call: search_call("Lightning Bolt", "Delver")
                                                                  if offers_tools(call) else cases[call.source["question"]][0]))) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        for question, (_, status) in cases.items():
            done = send_message(client, conversation_id, question)[-1]
            assert done["generation"]["status"] == status, question
            if status == "failed":
                assert SOL_RING not in json.dumps(done["generation"])
        assets = send_message(client, conversation_id, "assets from either search")[-1]["generation"]
        assert [asset["card_id"] for asset in assets["assets"]] == [DELVER, BOLT]


def test_nothing_relevant_completes_with_insufficient_evidence(tmp_path):
    path = tmp_path / "cards.db"
    ingest_sample(path)
    empty = ScriptedChatModel(script=[search_call("Zyzzyx"), search_call("Qwertyuiop"), "Nothing found."])
    with TestClient(create_app(path, chat_model=empty)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = send_message(client, conversation_id, "the zyzzyx card")
        assert [event["card_count"] for event in searches_of(events)] == [0, 0]
        done = events[-1]["generation"]
        assert done["status"] == "completed" and done["insufficient_evidence"] is True and done["citations"] == []
        assert not any(event["event"] == "delta" for event in events)

    weak = {"text": "None of the found cards is a blue counterspell.", "citations": [], "insufficient_evidence": True}
    model = ScriptedChatModel(script=[search_call("Lightning Bolt"), search_call("Sol Ring"), "Done.", weak])
    with TestClient(create_app(path, chat_model=model)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        done = send_message(client, conversation_id, "a blue counterspell")[-1]
        assert done["generation"]["status"] == "completed"
        assert done["generation"]["insufficient_evidence"] is True and done["generation"]["citations"] == []
        assert {card["card_id"] for card in done["trace"]["selected_evidence"]} == {BOLT, SOL_RING}


def test_reopening_after_a_restart_returns_every_search_of_every_turn(tmp_path):
    path = tmp_path / "cards.db"
    ingest_sample(path)
    answer = {"text": "Bolt and Sol Ring.", "citations": [BOLT, SOL_RING], "insufficient_evidence": False}
    model = ScriptedChatModel(script=[search_call("Lightning Bolt"), search_call("Sol Ring"), "Done.", answer,
                                      search_call("Delver"), "Done.", {"text": "Delver.", "citations": [DELVER], "insufficient_evidence": False}])
    with TestClient(create_app(path, chat_model=model)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        first = send_message(client, conversation_id, "Bolt and Sol Ring")
        second = send_message(client, conversation_id, "and Delver?")
    with TestClient(create_app(path, chat_model=ScriptedChatModel(script=[]))) as client:
        turns = client.get(f"/api/conversations/{conversation_id}").json()["turns"]
        assert [turn["state"] for turn in turns] == ["completed", "completed"]
        assert [[search["query"] for search in turn["trace"]["searches"]] for turn in turns] == [["Lightning Bolt", "Sol Ring"], ["Delver"]]
        assert turns[0]["trace"]["searches"] == [event["search"] for event in searches_of(first)]
        assert turns[1]["trace"]["searches"] == [event["search"] for event in searches_of(second)]
        assert [card["card_id"] for card in turns[0]["trace"]["selected_evidence"]] == [BOLT, SOL_RING]


def test_explicit_filters_and_the_search_mode_apply_to_every_search(tmp_path):
    from test_vectors import ControlledEmbedder

    path = tmp_path / "cards.db"
    ingest_sample(path, embedder=ControlledEmbedder())
    model = ScriptedChatModel(script=[search_call("Lightning Bolt"), search_call("Sol Ring", "Delver"),
                                      {"citations": [], "assets": [DELVER], "insufficient_evidence": False}])
    with TestClient(create_app(path, embedder=ControlledEmbedder(), chat_model=model)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = send_message(client, conversation_id, "bolt, ring and delver", mode="hybrid", filters={"colors": ["U"]})
        searches = searches_of(events)
        assert [search["query"] for search in searches] == ["Lightning Bolt", "Sol Ring", "Delver"]
        for search in searches:
            assert search["search"]["mode"] == "hybrid" and search["search"]["filters"] == {"colors": ["U"]}
            assert {card["card_id"] for cards in search["search"]["stages"].values() for card in cards} <= {DELVER}
        done = events[-1]
        assert done["generation"]["status"] == "completed"
        assert [card["card_id"] for card in done["trace"]["selected_evidence"]] == [DELVER]
        tool_results = " ".join(m.content for m in model.calls[1].messages if m.type == "tool")
        assert BOLT not in tool_results


def test_each_search_in_reranking_mode_keeps_its_own_reranking_changes_in_the_retrieval_details(tmp_path):
    from artifact_cards import ATOG, ENGINEER, TopicEmbedder, TopicReranker, seed_artifact_cards

    path = tmp_path / "cards.db"
    seed_artifact_cards(path)
    model = ScriptedChatModel(script=[search_call("creature gets +2/+2 until end of turn"), search_call("Atog"), DONE_SEARCHING,
                                      {"text": "Both sacrifice artifacts.", "citations": [ATOG, ENGINEER], "insufficient_evidence": False}])
    with TestClient(create_app(path, embedder=TopicEmbedder(), reranker=TopicReranker(), chat_model=model)) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = send_message(client, conversation_id, "artifact sacrifice creatures", mode="hybrid_rerank")
        done = events[-1]
        assert done["generation"]["status"] == "completed"
        saved = client.get(f"/api/conversations/{conversation_id}").json()["turns"][0]["trace"]["searches"]
    first, second = (event["search"] for event in searches_of(events))
    assert saved == [first, second]
    # The first search's wording favors Atog by keyword, but the reranker promotes Goblin Engineer.
    assert [card["card_id"] for card in first["stages"]["fused"]] == [ATOG, ENGINEER]
    assert [(card["card_id"], card["fused_rank"], card["rank_change"]) for card in first["stages"]["reranked"]] == [(ENGINEER, 2, 1), (ATOG, 1, -1)]
    assert [card["card_id"] for card in first["selected_evidence"]] == [ENGINEER, ATOG]
    # The second search ranks Atog first before and after reranking.
    assert [(card["card_id"], card["fused_rank"], card["rank_change"]) for card in second["stages"]["reranked"]] == [(ATOG, 1, 0), (ENGINEER, 2, 0)]
    for search in (first, second):
        assert search["mode"] == "hybrid_rerank"
        assert search["models"]["reranker"] == TopicReranker.config
        assert search["timings_ms"]["reranking"] >= 0
