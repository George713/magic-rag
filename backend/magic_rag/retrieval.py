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
