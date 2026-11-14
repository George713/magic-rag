"""Rank fusion combines positions; raw branch scores remain independent signals."""
def exact_name_match(name: str, query: str) -> bool:
    return name.strip().casefold() == query.strip().casefold()


def fuse(branches: dict[str, list[dict]], rank_constant: int = 60, *, query: str = "") -> list[dict]:
    cards = {}
    for branch, candidates in branches.items():
        for card in candidates:
            card_id = card["card_id"]
            if card_id not in cards:
                cards[card_id] = {**card, "score": 0.0, "signals": {}}
            fused = cards[card_id]
            fused["signals"][branch] = {"rank": card["rank"], "score": card["score"]}
            fused["score"] += 1.0 / (rank_constant + card["rank"])
    ordered = sorted(cards.values(), key=lambda card: (
        not exact_name_match(card["name"], query), -card["score"], card["card_id"]))
    return [{**card, "rank": rank} for rank, card in enumerate(ordered, 1)]


EVIDENCE_CAP_FACTOR = 2


def combined_evidence(searches):
    """Evidence for an answer: the union of every search's selected cards, deduplicated by card.

    Cards are taken by rank across searches (every search's best card, then every second-best, ...),
    first occurrence wins, up to a total cap of `EVIDENCE_CAP_FACTOR` times the per-search evidence
    limit, so each search keeps its best cards and the answer request stays bounded.
    """
    if not searches:
        return []
    cap = EVIDENCE_CAP_FACTOR * max(search["settings"]["evidence_limit"] for search in searches)
    seen = set()
    evidence = []
    for rank in range(max(len(search["selected_evidence"]) for search in searches)):
        for search in searches:
            cards = search["selected_evidence"]
            if rank < len(cards) and cards[rank]["card_id"] not in seen and len(evidence) < cap:
                seen.add(cards[rank]["card_id"])
                evidence.append(cards[rank])
    return evidence
