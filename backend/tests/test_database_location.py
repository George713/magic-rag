from magic_rag.app import default_db_path


def test_default_database_stays_in_project_when_started_elsewhere(monkeypatch, tmp_path, pytestconfig):
    monkeypatch.delenv("MAGIC_RAG_DB", raising=False)
    monkeypatch.chdir(tmp_path)
    assert default_db_path() == pytestconfig.rootpath / "data" / "cards.db"


def test_explicit_database_override_remains_available(monkeypatch, tmp_path):
    path = tmp_path / "isolated.db"
    monkeypatch.setenv("MAGIC_RAG_DB", str(path))
    assert default_db_path() == path
