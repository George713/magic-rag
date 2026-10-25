"""One exact candidate-eligibility contract shared by both retrieval branches."""
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Color = Literal["W", "U", "B", "R", "G"]
CardType = Literal["Artifact", "Battle", "Conspiracy", "Creature", "Dungeon", "Enchantment",
                   "Instant", "Kindred", "Land", "Phenomenon", "Plane", "Planeswalker",
                   "Scheme", "Sorcery", "Vanguard"]


class ExactFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    colors: list[Color] | None = None
    card_types: list[CardType] = Field(default_factory=list)
    legendary: bool = Field(default=False, strict=True)
    mana_value_min: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    mana_value_max: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def canonical(self):
        if self.mana_value_min is not None and self.mana_value_max is not None and self.mana_value_min > self.mana_value_max:
            raise ValueError("Minimum mana value must not exceed maximum mana value.")
        if self.colors is not None:
            self.colors = [color for color in ("W", "U", "B", "R", "G") if color in self.colors]
        self.card_types = sorted(set(self.card_types))
        return self

    def sql(self):
        clauses = []
        parameters = []
        if self.colors is not None:
            clauses.append("json_array_length(cards.colors) = ?")
            parameters.append(len(self.colors))
            for color in self.colors:
                clauses.append("EXISTS (SELECT 1 FROM json_each(cards.colors) WHERE value = ?)")
                parameters.append(color)
        if self.card_types:
            clauses.append("has_card_types(cards.type_line, ?) = 1")
            parameters.append(json.dumps(self.card_types))
        if self.legendary:
            clauses.append("has_card_types(cards.type_line, ?) = 1")
            parameters.append(json.dumps(["Legendary"]))
        if self.mana_value_min is not None:
            clauses.append("cards.mana_value >= ?")
            parameters.append(self.mana_value_min)
        if self.mana_value_max is not None:
            clauses.append("cards.mana_value <= ?")
            parameters.append(self.mana_value_max)
        return " AND ".join(clauses) or "1", parameters


def register_filter_functions(db):
    def has_card_types(type_line, requested):
        types = {word for face in type_line.split(" // ") for word in face.split("—", 1)[0].split()}
        return set(json.loads(requested)).issubset(types)
    db.create_function("has_card_types", 2, has_card_types, deterministic=True)
