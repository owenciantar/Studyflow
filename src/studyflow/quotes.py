"""Quote loading, pack filtering, and session closing messages."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import NamedTuple

_DATA_DIR = Path(__file__).parent / "data"

# Packs available at level 0 (always)
_BASE_PACKS = {"base"}

# Maps unlock name → pack key in quotes.json
_PACK_UNLOCK_MAP = {
    "growth":       "growth",
    "deep_work":    "deep_work",
    "perseverance": "perseverance",
}


class Quote(NamedTuple):
    text: str
    author: str


def _load_all() -> dict[str, list[Quote]]:
    with open(_DATA_DIR / "quotes.json", encoding="utf-8") as f:
        raw = json.load(f)
    return {
        pack: [Quote(q["text"], q["author"]) for q in quotes]
        for pack, quotes in raw["packs"].items()
    }


_ALL_QUOTES: dict[str, list[Quote]] | None = None


def _quotes() -> dict[str, list[Quote]]:
    global _ALL_QUOTES
    if _ALL_QUOTES is None:
        _ALL_QUOTES = _load_all()
    return _ALL_QUOTES


def get_available_quotes(unlocked_pack_names: list[str] | None = None) -> list[Quote]:
    """Return all quotes from unlocked packs, shuffled."""
    all_q = _quotes()
    available_packs = set(_BASE_PACKS)

    if unlocked_pack_names:
        for name in unlocked_pack_names:
            pack_key = _PACK_UNLOCK_MAP.get(name)
            if pack_key:
                available_packs.add(pack_key)

    pool: list[Quote] = []
    for pack in available_packs:
        pool.extend(all_q.get(pack, []))

    random.shuffle(pool)
    return pool


def closing_message(duration_seconds: int) -> str:
    """Return a short congratulatory message scaled to session length."""
    minutes = duration_seconds // 60
    if minutes >= 90:
        msgs = [
            "Outstanding depth. That session will compound.",
            "90+ minutes of focus. Your future self thanks you.",
            "Exceptional. That's the kind of work that changes things.",
        ]
    elif minutes >= 50:
        msgs = [
            "Solid deep work. Well done.",
            "Great session. Consistency beats intensity — you're doing both.",
            "That's the work. Keep showing up.",
        ]
    elif minutes >= 25:
        msgs = [
            "Good work. Every session builds the habit.",
            "Nice focus. The streak continues.",
            "Progress made. See you next session.",
        ]
    else:
        msgs = [
            "A short session is better than none. Keep going.",
            "Every minute counts. You showed up.",
            "Small steps, steady forward.",
        ]
    return random.choice(msgs)
