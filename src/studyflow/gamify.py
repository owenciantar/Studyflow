"""XP calculation, level thresholds, streak logic, and unlock gating."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

from studyflow import db


# ---------------------------------------------------------------------------
# XP
# ---------------------------------------------------------------------------

def calc_xp(duration_seconds: int) -> int:
    """1 XP/min with depth bonuses: +20% at ≥50 min, +50% at ≥90 min."""
    minutes = duration_seconds / 60.0
    if minutes >= 90:
        multiplier = 1.5
    elif minutes >= 50:
        multiplier = 1.2
    else:
        multiplier = 1.0
    return math.floor(minutes * multiplier)


# ---------------------------------------------------------------------------
# Levels  — level N requires sum(i*100 for i in 1..N) cumulative XP
# ---------------------------------------------------------------------------

def level_threshold(n: int) -> int:
    """Total XP needed to *reach* level n (0-indexed: level 0 = starting)."""
    if n <= 0:
        return 0
    return n * (n + 1) * 50  # sum(i*100 for i in 1..n) = 100 * n*(n+1)/2


def xp_to_level(total_xp: int) -> tuple[int, int, int]:
    """Return (level, xp_into_current_level, xp_needed_for_next_level)."""
    level = 0
    while level_threshold(level + 1) <= total_xp:
        level += 1
    prev = level_threshold(level)
    nxt = level_threshold(level + 1)
    return level, total_xp - prev, nxt - prev


# ---------------------------------------------------------------------------
# Streaks
# ---------------------------------------------------------------------------

def compute_streak(daily_totals: dict[date, int], daily_goal_seconds: int) -> tuple[int, int]:
    """Return (current_streak, longest_streak) from precomputed daily totals."""
    if not daily_totals:
        return 0, 0

    today = date.today()
    goal_days: set[date] = {d for d, secs in daily_totals.items() if secs >= daily_goal_seconds}

    # Current streak: walk backwards from today (or yesterday if today not yet complete)
    start_offset = 0 if today in goal_days else 1
    current = 0
    last_grace_offset: int | None = None

    for i in range(366):
        offset = start_offset + i
        d = today - timedelta(days=offset)
        if d in goal_days:
            current += 1
        else:
            # Grace day: allowed once per 7-day window, only when streak ≥ 7
            can_grace = current >= 7 and (
                last_grace_offset is None or (offset - last_grace_offset) >= 7
            )
            if can_grace:
                last_grace_offset = offset
                current += 1
            else:
                break

    # Longest streak: longest consecutive run of goal_days
    sorted_days = sorted(goal_days)
    longest = run = (1 if sorted_days else 0)
    for i in range(1, len(sorted_days)):
        if (sorted_days[i] - sorted_days[i - 1]).days == 1:
            run += 1
            if run > longest:
                longest = run
        else:
            run = 1

    return current, max(longest, current)


@dataclass
class StreakInfo:
    current: int
    longest: int
    goal_hit_today: bool
    minutes_today: int
    goal_minutes: int


def get_streak_info() -> StreakInfo:
    daily_goal_minutes = int(db.get_state("daily_goal_minutes", "120"))
    daily_goal_seconds = daily_goal_minutes * 60
    daily_totals = db.get_daily_totals(days=365)
    today_secs = daily_totals.get(date.today(), 0)
    current, longest = compute_streak(daily_totals, daily_goal_seconds)
    return StreakInfo(
        current=current,
        longest=longest,
        goal_hit_today=today_secs >= daily_goal_seconds,
        minutes_today=today_secs // 60,
        goal_minutes=daily_goal_minutes,
    )


# ---------------------------------------------------------------------------
# Unlocks
# ---------------------------------------------------------------------------

# Maps level → list of (kind, name) to grant on reaching that level
LEVEL_UNLOCKS: dict[int, list[tuple[str, str]]] = {
    2:  [("garden", "sprout"),       ("quote_pack", "growth")],
    5:  [("garden", "seedling"),     ("quote_pack", "deep_work"), ("theme", "ember")],
    8:  [("garden", "sapling"),      ("theme", "ocean")],
    10: [("quote_pack", "perseverance")],
    15: [("garden", "young_tree"),   ("theme", "forest")],
    20: [("garden", "mature_tree")],
    30: [("garden", "flowering_tree"), ("theme", "midnight")],
    50: [("garden", "ancient_tree")],
}


def check_and_apply_unlocks(new_level: int) -> list[tuple[str, str]]:
    """Grant any unlocks up to new_level; return newly granted ones."""
    existing = {(u["kind"], u["name"]) for u in db.get_unlocks()}
    granted: list[tuple[str, str]] = []
    for lvl in range(1, new_level + 1):
        for kind, name in LEVEL_UNLOCKS.get(lvl, []):
            if (kind, name) not in existing:
                db.add_unlock(kind, name)
                granted.append((kind, name))
    return granted


# ---------------------------------------------------------------------------
# Session XP application (dry-run — caller handles DB write)
# ---------------------------------------------------------------------------

@dataclass
class XPResult:
    xp_earned: int
    new_total_xp: int
    old_level: int
    new_level: int
    xp_into: int
    xp_needed: int
    leveled_up: bool
    new_unlocks: list[tuple[str, str]]


def calc_session_xp_result(duration_seconds: int) -> XPResult:
    """Compute XP result without writing to DB."""
    xp = calc_xp(duration_seconds)
    current_total = int(db.get_state("total_xp", "0"))
    new_total = current_total + xp
    old_level, _, _ = xp_to_level(current_total)
    new_level, xp_into, xp_needed = xp_to_level(new_total)
    return XPResult(
        xp_earned=xp,
        new_total_xp=new_total,
        old_level=old_level,
        new_level=new_level,
        xp_into=xp_into,
        xp_needed=xp_needed,
        leveled_up=new_level > old_level,
        new_unlocks=[],  # populated after DB write
    )
