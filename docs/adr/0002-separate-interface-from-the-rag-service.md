# Separate the SvelteKit interface from the Python RAG service

SvelteKit handles chat presentation and forwards requests to a local Python FastAPI service, which owns ingestion, retrieval, local models, answer-provider integration, and persistence. This gives the learning project one inspectable RAG pipeline with direct access to Python's model ecosystem, at the cost of running two application processes rather than using a single Node.js application.
