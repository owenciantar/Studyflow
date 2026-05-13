"""Flowtime session: live rich display and raw-mode keypress handling."""

from __future__ import annotations

import select
import signal
import sys
import termios
import threading
import time
import tty
from datetime import datetime, timezone
from types import FrameType

from rich.console import Console
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.text import Text

from studyflow import db, gamify, garden, quotes

MIN_SESSION_SECONDS = 5 * 60
QUOTE_INTERVAL = 5 * 60   # seconds between quote rotations
WATER_INTERVAL = 10 * 60  # seconds between watering droplets
GOAL_BANNER_SECS = 30     # how long to show goal-hit banner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_time(seconds: float) -> str:
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _bar(filled: int, total: int, width: int = 22) -> str:
    n = round(width * filled / total) if total else 0
    n = max(0, min(n, width))
    return "[green]" + "█" * n + "[dim white]" + "░" * (width - n) + "[/]"


# ---------------------------------------------------------------------------
# Live display
# ---------------------------------------------------------------------------

def _build_panel(
    *,
    elapsed: float,
    tag: str | None,
    quote: quotes.Quote,
    today_total_secs: int,
    daily_goal_min: int,
    total_xp: int,
    lifetime_hours: float,
    goal_hit_at: float | None,
) -> Panel:
    stage = garden.stage_for_hours(lifetime_hours)

    xp_preview = gamify.calc_xp(int(elapsed))
    level, xp_into, xp_needed = gamify.xp_to_level(total_xp)

    today_min = today_total_secs // 60
    goal_min = daily_goal_min
    goal_pct = min(today_min / goal_min, 1.0) if goal_min else 0.0

    droplets = "💧" * min(int(elapsed // WATER_INTERVAL), 5)
    goal_just_hit = goal_hit_at is not None and (elapsed - goal_hit_at) < GOAL_BANNER_SECS

    lines: list[str] = [""]

    if goal_just_hit:
        lines.append("  [bold yellow]🎉  DAILY GOAL REACHED! AMAZING! 🎉[/]")
        lines.append("")

    # Elapsed timer
    lines.append(f"  [bold green]⏱   {_fmt_time(elapsed)}[/]")
    lines.append("")

    # XP preview + level bar
    lines.append(f"  [yellow]+{xp_preview} XP[/] [dim]pending[/]   [cyan]Level {level}[/]")
    lines.append(f"  {_bar(xp_into, xp_needed)}  {xp_into}/{xp_needed} XP")
    lines.append("")

    # Daily goal progress
    remaining = max(0, goal_min - today_min)
    lines.append(
        f"  Today: [bold]{today_min}[/] / {goal_min} min  "
        f"{_bar(today_min, goal_min, 18)}  {goal_pct:.0%}"
    )
    if remaining:
        lines.append(f"  [dim]{remaining} min from daily goal[/]")
    else:
        lines.append("  [green]Daily goal achieved! ✓[/]")
    lines.append("")

    # Garden
    if droplets:
        lines.append(f"  {droplets}")
    for art_line in stage.art.splitlines():
        lines.append(f"  {escape(art_line)}")
    lines.append(f"  [dim]{stage.label}[/]")
    lines.append("")

    # Quote
    lines.append(f'  [italic dim]"{quote.text}"[/]')
    lines.append(f"  [dim]— {quote.author}[/]")
    lines.append("")

    # Footer hint
    tag_hint = f" [dim]·[/] [cyan]{tag}[/]" if tag else ""
    lines.append(f"  [dim][[bold white]s[/]] save & earn XP    [[bold white]q[/]] quit without XP[/]{tag_hint}")
    lines.append("")

    title = Text("StudyFlow", style="bold magenta")
    return Panel(
        "\n".join(lines),
        title=title,
        border_style="magenta",
        padding=(0, 1),
    )


# ---------------------------------------------------------------------------
# Key reader thread
# ---------------------------------------------------------------------------

def _start_key_reader(
    stop_event: threading.Event,
    action: list[str],
) -> threading.Thread:
    """Spawn a daemon thread that reads s/q/^C from stdin in raw mode."""

    def _run() -> None:
        if not sys.stdin.isatty():
            return
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)  # preserves output processing so rich cursor-up works
            while not stop_event.is_set():
                ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                if ready:
                    ch = sys.stdin.read(1)
                    if ch == "s":
                        action[0] = "save"
                        stop_event.set()
                        break
                    elif ch == "q":
                        action[0] = "quit"
                        stop_event.set()
                        break
        except Exception:
            pass
        finally:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            except Exception:
                pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_session(tag: str | None = None) -> None:
    """Start a flowtime session with a live display. Blocks until s/q/Ctrl+C."""
    db.init_db()

    start_utc = datetime.now(timezone.utc)
    start_mono = time.monotonic()

    base_today_secs = db.get_today_seconds()
    daily_goal_min = int(db.get_state("daily_goal_minutes", "120"))
    total_xp = int(db.get_state("total_xp", "0"))
    lifetime_hours = db.get_lifetime_hours()

    # Load unlocked quote packs
    unlocked = [u["name"] for u in db.get_unlocks() if u["kind"] == "quote_pack"]
    quote_pool = quotes.get_available_quotes(unlocked)
    if not quote_pool:
        quote_pool = quotes.get_available_quotes()

    stop_event = threading.Event()
    action: list[str] = ["quit"]

    def _sigint_handler(sig: int, frame: FrameType | None) -> None:
        action[0] = "quit"
        stop_event.set()

    old_sigint = signal.signal(signal.SIGINT, _sigint_handler)
    key_thread = _start_key_reader(stop_event, action)

    console = Console()
    goal_hit_at: float | None = None

    with Live(console=console, refresh_per_second=2, screen=False) as live:
        while not stop_event.is_set():
            elapsed = time.monotonic() - start_mono
            today_total = base_today_secs + int(elapsed)

            if goal_hit_at is None and (today_total // 60) >= daily_goal_min:
                goal_hit_at = elapsed

            quote_idx = int(elapsed // QUOTE_INTERVAL) % len(quote_pool)
            current_quote = quote_pool[quote_idx]

            live.update(
                _build_panel(
                    elapsed=elapsed,
                    tag=tag,
                    quote=current_quote,
                    today_total_secs=today_total,
                    daily_goal_min=daily_goal_min,
                    total_xp=total_xp,
                    lifetime_hours=lifetime_hours,
                    goal_hit_at=goal_hit_at,
                )
            )
            stop_event.wait(timeout=0.5)

        # Ensure key reader restores terminal before Live exits
        key_thread.join(timeout=0.5)

    signal.signal(signal.SIGINT, old_sigint)

    end_utc = datetime.now(timezone.utc)
    elapsed_final = time.monotonic() - start_mono
    duration = int(elapsed_final)

    # --- Handle quit / too short ---
    if action[0] == "quit":
        if duration < MIN_SESSION_SECONDS:
            console.print(
                "\n[yellow]Session abandoned — no XP awarded.[/]"
                " (Less than 5 minutes studied.)"
            )
        else:
            db.record_abandoned(start_utc, end_utc, duration, tag)
            console.print("\n[yellow]Session abandoned — no XP awarded.[/]")
        return

    if duration < MIN_SESSION_SECONDS:
        console.print(
            "\n[yellow]Session too short (< 5 min) — not recorded.[/]"
        )
        return

    # --- Save session ---
    xp_result = gamify.calc_session_xp_result(duration)
    db.save_session_and_xp(
        started_at=start_utc,
        ended_at=end_utc,
        duration_seconds=duration,
        tag=tag,
        xp_earned=xp_result.xp_earned,
        new_total_xp=xp_result.new_total_xp,
    )
    new_unlocks = gamify.check_and_apply_unlocks(xp_result.new_level)

    streak = gamify.get_streak_info()
    minutes = duration // 60
    remaining = max(0, streak.goal_minutes - streak.minutes_today - minutes)

    console.print(
        f"\n[bold green]✓ Session saved![/]  "
        f"[yellow]+{xp_result.xp_earned} XP[/]  "
        f"[dim]({minutes} min · Level {xp_result.new_level})[/]"
    )

    if remaining > 0:
        console.print(f"[dim]{remaining} min from today's goal · Streak: {streak.current}d[/]")
    else:
        console.print(f"[green]Daily goal hit! 🔥 Streak: {streak.current}d[/]")

    if xp_result.leveled_up:
        console.print(
            f"[bold yellow]⬆  Level up! You are now Level {xp_result.new_level}![/]"
        )

    for kind, name in new_unlocks:
        console.print(f"[magenta]🔓 Unlocked: {kind} — {name}[/]")

    closing = quotes.closing_message(duration)
    console.print(f"\n[italic dim]{closing}[/]\n")
