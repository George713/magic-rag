# Use SQLite for all local persistence

Store cards, embeddings, conversations, and retrieval traces in SQLite, using FTS5 for BM25 keyword retrieval and sqlite-vec for vector retrieval. This keeps persistence in one embedded database instead of splitting retrieval and chat history between LanceDB and SQLite, at the cost of integrating the retrieval branches and fusion explicitly in Python. SQLite runs directly within the application against a local file, without Docker or a database server.
