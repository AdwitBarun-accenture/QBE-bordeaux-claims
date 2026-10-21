"""Loads reference data (code lists, FX, CRESTA, aliases) from app/reference_data.
Swap these JSON files for your real market reference data; nothing is hard-coded
inside the agents."""
import json
from functools import lru_cache
from pathlib import Path

REF_DIR = Path(__file__).resolve().parent.parent / "reference_data"


@lru_cache
def load_ref(name: str):
    with open(REF_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def reload_all():
    load_ref.cache_clear()
