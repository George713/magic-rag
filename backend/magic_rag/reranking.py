"""Independent query/document cross-encoder boundary."""
import math
import os
from pathlib import Path
from typing import Protocol


class RerankingError(ValueError):
    pass


class Reranker(Protocol):
    @property
    def config(self) -> dict: ...
    def score(self, query: str, documents: list[str]) -> list[float]: ...


def card_document(card):
    return "\n".join([card["name"], card["mana_cost"], card["type_line"], " ".join(card["colors"]), card["text"]])


def rerank(query: str, candidates: list[dict], model: Reranker) -> list[dict]:
    if not candidates:
        return []
    scores = model.score(query, [card_document(card) for card in candidates])
    if len(scores) != len(candidates) or not all(math.isfinite(float(score)) for score in scores):
        raise RerankingError("Reranker must return one finite score for every shortlisted card.")
    scored = [{**card, "fusion_score":card["score"], "fused_rank":card["rank"], "score":float(score)}
              for card, score in zip(candidates, scores)]
    ordered = sorted(scored, key=lambda card: (-card["score"], card["card_id"]))
    return [{**card, "rank":rank, "rank_change":card["fused_rank"] - rank} for rank, card in enumerate(ordered, 1)]


class MiniLmReranker:
    def __init__(self, device: str | None = None, revision: str | None = None):
        self.device = device or os.environ.get("MAGIC_RAG_RERANKER_DEVICE", os.environ.get("MAGIC_RAG_DEVICE", "cpu"))
        self.revision = revision or os.environ.get("MAGIC_RAG_RERANKER_REVISION", "main")
        self._model = None

    @property
    def model(self):
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                from huggingface_hub import hf_hub_download
                from torch.nn import Identity
            except ImportError as exc:
                raise RerankingError("Local reranker is not installed. Run uv sync --extra models --python 3.11.") from exc
            try:
                name = "cross-encoder/ms-marco-MiniLM-L6-v2"
                config_path = hf_hub_download(name, "config.json", revision=self.revision)
                self._resolved_revision = Path(config_path).parent.name
                if len(self._resolved_revision) != 40:
                    raise RerankingError("Reranker snapshot did not expose an immutable revision.")
                self._model = CrossEncoder(name, revision=self._resolved_revision, device=self.device, activation_fn=Identity())
            except Exception as exc:
                raise RerankingError("Unable to acquire/load the local reranker. Check download access and device settings; other retrieval modes remain available.") from exc
        return self._model

    @property
    def config(self):
        model = self.model
        return {"model":"cross-encoder/ms-marco-MiniLM-L6-v2", "revision":self._resolved_revision,
                "max_tokens":min(int(model.tokenizer.model_max_length), int(model.model.config.max_position_embeddings)),
                "activation":"identity", "input_policy":"reject-overlength", "score":"unbounded relevance logit (higher is better)"}

    def score(self, query: str, documents: list[str]):
        model = self.model
        limit = self.config["max_tokens"]
        for document in documents:
            count = len(model.tokenizer.encode(query, document, add_special_tokens=True, truncation=False))
            if count > limit:
                raise RerankingError(f"Reranker query/card pair is {count} tokens; limit is {limit}. Evidence was not truncated.")
        if not documents:
            return []
        return model.predict([(query, document) for document in documents], show_progress_bar=False).tolist()
