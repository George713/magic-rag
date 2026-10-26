"""Repair the legacy corpus and saved selections through the public API."""
import sqlite3

from fastapi.testclient import TestClient

from magic_rag.app import create_app
from magic_rag.ingest import ingest_sample


class ImageSource:
    def snapshot(self):
        return {'id': 'image-source'}, [{
            'oracle_id': 'sample-delver', 'name': 'Delver',
            'scryfall_uri': 'https://cards.example/delver',
            'card_faces': [
                {'name': 'Front', 'image_uris': {'normal': 'https://cards.example/front.jpg'}},
                {'name': 'Back', 'image_uris': {'normal': 'https://cards.example/back.jpg'}},
            ],
        }]


class AssetProvider:
    def answer(self, question, evidence, session_id, **kwargs):
        return {'text': 'Recommended.', 'assets': ['sample-delver'], 'citations': ['sample-delver']}


def test_repair_fills_legacy_evidence_and_selected_assets_without_reindexing(tmp_path):
    path = tmp_path / 'cards.db'
    ingest_sample(path)
    with TestClient(create_app(path, provider=AssetProvider(), corpus_source=ImageSource())) as client:
        chat = client.post('/api/conversations').json()['id']
        original = client.post('/api/search', json={'question': 'Delver', 'conversation_id': chat, 'generate_answer': True}).json()
        assert original['generation']['assets'][0]['images'] == []
        corpus = client.get('/api/corpus').json()
        # A legacy snapshot may refer to a card no longer in the active corpus.
        with sqlite3.connect(path) as db:
            db.execute("DELETE FROM cards WHERE card_id = 'sample-delver'")
        repaired = client.post('/api/corpus/repair-images')
        assert repaired.status_code == 200
        assert repaired.json()['repaired_turns'] == 1
        saved = client.get(f'/api/conversations/{chat}').json()['turns'][0]['trace']
        images = saved['generation']['assets'][0]['images']
        assert len(images) == 2
        assert images[1]['url'] == 'https://cards.example/back.jpg'
        assert saved['selected_evidence'][0]['images'] == images
        assert saved['stages']['keyword'][0]['images'] == images
        assert saved['generation']['text'] == original['generation']['text']
        assert saved['generation']['citations'] == original['generation']['citations']
        assert saved['mode'] == original['mode']
        assert saved['selected_evidence'][0]['text'] == original['selected_evidence'][0]['text']
        assert client.get('/api/corpus').json() == corpus
        # Repeat repairs preserve historical image snapshots and selections.
        assert client.post('/api/corpus/repair-images').json()['repaired_turns'] == 0
    with TestClient(create_app(path)) as restarted:
        assert restarted.get(f'/api/conversations/{chat}').json()['turns'][0]['trace'] == saved


def test_repair_supplies_future_searches_preserves_existing_images_and_rolls_back_failure(tmp_path):
    path = tmp_path / 'cards.db'
    ingest_sample(path)
    source = ImageSource()
    with TestClient(create_app(path, corpus_source=source)) as client:
        assert client.post('/api/corpus/repair-images').status_code == 200
        before = client.post('/api/search', json={'question': 'Delver'}).json()['selected_evidence'][0]
        assert len(before['images']) == 2
        metadata, records = source.snapshot()
        records[0]['card_faces'][0]['image_uris']['normal'] = 'https://cards.example/replacement.jpg'
        source.snapshot = lambda: (metadata, records)
        assert client.post('/api/corpus/repair-images').status_code == 200
        assert client.post('/api/search', json={'question': 'Delver'}).json()['selected_evidence'][0] == before
        def fail():
            raise RuntimeError('download failed')
        source.snapshot = fail
        assert client.post('/api/corpus/repair-images').status_code == 422
        assert client.post('/api/search', json={'question': 'Delver'}).json()['selected_evidence'][0] == before


def test_repair_rejects_unusable_source_and_database_failure_is_atomic(tmp_path):
    path = tmp_path / 'cards.db'
    ingest_sample(path)
    source = ImageSource()
    with TestClient(create_app(path, provider=AssetProvider(), corpus_source=source)) as client:
        chat = client.post('/api/conversations').json()['id']
        original = client.post('/api/search', json={'question': 'Delver', 'conversation_id': chat, 'generate_answer': True}).json()
        with sqlite3.connect(path) as db:
            db.execute("CREATE TRIGGER reject_repair BEFORE UPDATE ON conversation_turns BEGIN SELECT RAISE(ABORT, 'repair failed'); END")
        assert client.post('/api/corpus/repair-images').status_code == 422
        assert client.get(f'/api/conversations/{chat}').json()['turns'][0]['trace'] == original
        assert client.post('/api/search', json={'question': 'Delver'}).json()['selected_evidence'][0]['images'] == []
        source.snapshot = lambda: ({'id': 'empty'}, [])
        assert client.post('/api/corpus/repair-images').status_code == 422


def test_repair_rejects_unsafe_urls_and_leaves_existing_snapshots_unchanged(tmp_path):
    path = tmp_path / 'cards.db'
    ingest_sample(path)
    source = ImageSource()
    metadata, records = source.snapshot()
    records[0]['card_faces'][0]['image_uris']['normal'] = 'javascript:alert(1)'
    records[0]['scryfall_uri'] = 'https://user:secret@cards.example/private'
    source.snapshot = lambda: (metadata, records)
    with TestClient(create_app(path, corpus_source=source)) as client:
        assert client.post('/api/corpus/repair-images').status_code == 200
        card = client.post('/api/search', json={'question': 'Delver'}).json()['selected_evidence'][0]
        assert card['images'] == [{'name': 'Back', 'url': 'https://cards.example/back.jpg'}]
        assert card['source_url'] is None
