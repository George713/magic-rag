"""Cover the original text exactly; token budgets never imply text truncation."""
def token_windows(text, tokenizer, budget: int, error_type=ValueError):
    if budget < 1:
        raise error_type("The query leaves no token budget for card evidence; shorten the query. Evidence was not truncated.")
    remaining = text
    windows = []
    while remaining:
        encoding = tokenizer(remaining, add_special_tokens=False, truncation=False, return_offsets_mapping=True)
        offsets = encoding["offset_mapping"]
        if len(encoding["input_ids"]) <= budget:
            windows.append(remaining)
            break
        target = min(budget, len(offsets))
        while target:
            end = offsets[target - 1][1]
            candidate = remaining[:end]
            if end > 0 and len(tokenizer.encode(candidate, add_special_tokens=False, truncation=False)) <= budget:
                break
            target -= 1
        if not target:
            raise error_type("A text segment cannot fit the model token budget; evidence was not truncated.")
        windows.append(candidate)
        remaining = remaining[end:]
    return windows or [""]
