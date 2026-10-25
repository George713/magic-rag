# Exact card filters

Filters are explicit controls; search text and query rewriting never change them. The same constraints apply to keyword and vector candidate eligibility before ranking limits, so fusion and reranking only see eligible cards. Changing or clearing controls affects subsequent searches; each saved trace retains its own filter snapshot.

## Matching semantics

- **Colors:** `null` means any colors. An empty selected set means colorless. A nonempty set matches exactly those card colors: selecting blue and red includes blue-red cards and excludes mono-blue and three-color cards. This is card color, not commander color identity. Multi-face cards use the canonical combined colors stored during ingestion.
- **Card types:** every selected type must occur among the card's canonical type words, before the subtype separator `—`. For example, Artifact + Creature requires both types; selecting Creature never matches a creature subtype alone. Across a multi-face card, types are the union of face types. No selected type means any type.
- **Mana value:** minimum and maximum are inclusive nonnegative decimal boundaries. Either may be omitted. `0` is a real boundary, not an empty value. Fractional mana values remain supported. A minimum greater than the maximum is rejected.
- Constraints combine with AND. An empty filter object means no constraints. No matches is a successful empty retrieval, not a provider or service failure.

The API accepts `filters` on `POST /api/search`: `{ "colors": ["U", "R"], "card_types": ["Artifact", "Creature"], "mana_value_min": 0, "mana_value_max": 3.5 }`. Use canonical type names and color codes W/U/B/R/G. Omitted colors differ from `[]`. Unknown colors/types, nonfinite bounds, and reversed ranges return validation errors rather than silently changing the request.

The browser retains active controls across searches and follow-ups until changed or cleared. Reopening a historical turn displays that turn's recorded constraints in the inspector and restores its controls for the next search.
