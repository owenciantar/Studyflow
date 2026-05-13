"""ASCII plant stages tied to cumulative lifetime study hours."""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Stage definitions
# ---------------------------------------------------------------------------

@dataclass
class Stage:
    name: str
    label: str
    min_hours: float
    art: str


_SEED = """\
   ___
  /   \\
  \\___/"""

_SPROUT = """\
    ,
   \\|/
    |
  ~~·~~"""

_SEEDLING = """\
   \\|/
  -(·)-
   /|\\
    |
  ~~·~~"""

_SAPLING = """\
   \\|/
   (*)
  / | \\
    |
  __|__"""

_YOUNG_TREE = """\
   \\|||/
  -(***)-
   /   \\
   |   |
  _|___|_"""

_MATURE_TREE = """\
  \\\\|||//
 -(*****)-
  -(***)-
   |   |
  _|___|_"""

_FLOWERING_TREE = """\
 *\\\\|||//*
 *(******)*
  -(****)-
   | | |
  _|_|_|_"""

_ANCIENT_TREE = """\
@*\\\\|||//*@
@*(******)*@
@-(*****)- @
  @ | | @
 @_|_|_|_@"""


STAGES: list[Stage] = [
    Stage("seed",          "Seed",          0.0,   _SEED),
    Stage("sprout",        "Sprout",        1.0,   _SPROUT),
    Stage("seedling",      "Seedling",      5.0,   _SEEDLING),
    Stage("sapling",       "Sapling",       15.0,  _SAPLING),
    Stage("young_tree",    "Young Tree",    40.0,  _YOUNG_TREE),
    Stage("mature_tree",   "Mature Tree",   100.0, _MATURE_TREE),
    Stage("flowering_tree","Flowering Tree",250.0, _FLOWERING_TREE),
    Stage("ancient_tree",  "Ancient Tree",  500.0, _ANCIENT_TREE),
]


def stage_for_hours(lifetime_hours: float) -> Stage:
    """Return the appropriate growth stage for the given lifetime hours."""
    current = STAGES[0]
    for stage in STAGES:
        if lifetime_hours >= stage.min_hours:
            current = stage
    return current


def next_stage(current: Stage) -> Stage | None:
    """Return the next stage after current, or None if at max."""
    idx = next((i for i, s in enumerate(STAGES) if s.name == current.name), -1)
    if idx < 0 or idx >= len(STAGES) - 1:
        return None
    return STAGES[idx + 1]


def hours_to_next_stage(lifetime_hours: float) -> float | None:
    """Hours remaining until the next garden stage unlocks."""
    current = stage_for_hours(lifetime_hours)
    nxt = next_stage(current)
    if nxt is None:
        return None
    return max(0.0, nxt.min_hours - lifetime_hours)
