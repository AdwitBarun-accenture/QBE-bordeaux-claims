"""Cleansing/enrichment step framework. Each step mutates a canonical row and
returns lineage entries so every changed value can be traced (old -> new, why)."""
from dataclasses import dataclass, field


@dataclass
class StepContext:
    file_type: str
    date_order: str = "dmy"
    coverholder: str = ""
    stats: dict = field(default_factory=dict)


@dataclass
class Change:
    row: int
    field: str
    old: str
    new: str
    step: str

    def to_dict(self):
        return {"row": self.row, "field": self.field, "old": self.old, "new": self.new, "step": self.step}


class Step:
    name = "step"
    description = ""
    applies_to: tuple[str, ...] = ("premium", "claims")

    def apply(self, row: dict, ctx: StepContext) -> list[Change]:
        raise NotImplementedError

    @staticmethod
    def set(row: dict, field: str, new, step: str) -> list[Change]:
        old = row.get(field, "")
        new = "" if new is None else str(new)
        if str(old) == new:
            return []
        row[field] = new
        return [Change(row.get("_row", 0), field, str(old), new, step)]
