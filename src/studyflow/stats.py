"""Aggregation queries and rich dashboard rendering."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta

from rich.columns import Columns
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from studyflow import db, gamify, garden


def _bar(filled: int, total: int, width: int = 20) -> str:
    n = round(width * filled / total) if total else 0
    n = max(0, min(n, width))
    return "█" * n + "░" * (width - n)


def _duration_str(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def render_dashboard(console: Console) -> None:
    """Print the full stats dashboard to the given console."""
    db.init_db()

    total_xp = int(db.get_state("total_xp", "0"))
    daily_goal_min = int(db.get_state("daily_goal_minutes", "120"))
    level, xp_into, xp_needed = gamify.xp_to_level(total_xp)
    streak = gamify.get_streak_info()

    sessions_all = db.get_sessions(days=365)
    lifetime_hours = db.get_lifetime_hours()
    stage = garden.stage_for_hours(lifetime_hours)

    # ------------------------------------------------------------------
    # Header: level + XP bar + streak
    # ------------------------------------------------------------------
    bar_width = 30
    xp_bar = _bar(xp_into, xp_needed, bar_width)
    fire = "🔥" if streak.current >= 3 else "·"

    header_markup = (
        f"[bold cyan]Level {level}[/]  [{xp_bar}]  {xp_into}/{xp_needed} XP\n"
        f"[yellow]{fire} Streak: {streak.current}d[/]  [dim]Best: {streak.longest}d[/]"
    )
    console.print(Panel(header_markup, title="[bold magenta]StudyFlow[/]", border_style="magenta"))

    # ------------------------------------------------------------------
    # Today + Totals (side by side)
    # ------------------------------------------------------------------
    today_goal_bar = _bar(streak.minutes_today, streak.goal_minutes, 20)
    today_pct = min(streak.minutes_today / streak.goal_minutes, 1.0) if streak.goal_minutes else 0
    today_date = date.today()
    sessions_today_count = sum(
        1 for s in sessions_all
        if datetime.fromisoformat(s["started_at"]).astimezone().date() == today_date
    )

    today_colour = "green" if today_pct >= 1 else "yellow"
    today_markup = (
        f"[bold]{streak.minutes_today} / {streak.goal_minutes} min[/]\n"
        f"[{today_colour}][{today_goal_bar}] {today_pct:.0%}[/]\n"
        f"[dim]{sessions_today_count} session(s) today[/]"
    )

    # Period totals
    week_secs = sum(
        s["duration_seconds"] for s in sessions_all
        if (today_date - datetime.fromisoformat(s["started_at"]).astimezone().date()).days < 7
    )
    month_secs = sum(
        s["duration_seconds"] for s in sessions_all
        if (today_date - datetime.fromisoformat(s["started_at"]).astimezone().date()).days < 30
    )
    avg_secs = (
        sum(s["duration_seconds"] for s in sessions_all) // len(sessions_all)
        if sessions_all else 0
    )

    tags: list[str] = [s["tag"] for s in sessions_all if s["tag"]]
    top_tags = [t for t, _ in Counter(tags).most_common(3)]
    top_tags_str = ", ".join(top_tags) if top_tags else "—"

    totals_markup = (
        f"[bold]Lifetime: {lifetime_hours:.1f} h[/]\n"
        f"This week: {_duration_str(week_secs)}\n"
        f"This month: {_duration_str(month_secs)}\n"
        f"Sessions: {len(sessions_all)}  Avg: {_duration_str(avg_secs)}\n"
        f"[dim]Top tags: {top_tags_str}[/]"
    )

    console.print(
        Columns(
            [
                Panel(today_markup, title="[bold]Today[/]", border_style="cyan", width=36),
                Panel(totals_markup, title="[bold]Totals[/]", border_style="blue", width=38),
            ]
        )
    )

    # ------------------------------------------------------------------
    # Last 14 days bar chart
    # ------------------------------------------------------------------
    daily_totals = db.get_daily_totals(days=14)
    chart_lines: list[str] = []
    for i in range(13, -1, -1):
        d = today_date - timedelta(days=i)
        secs = daily_totals.get(d, 0)
        mins = secs // 60
        pct = min(mins / daily_goal_min, 1.0) if daily_goal_min else 0
        bar_len = round(pct * 28)
        colour = "green" if pct >= 1.0 else ("yellow" if pct > 0 else "dim")
        bar_str = f"[{colour}]{'█' * bar_len}{'░' * (28 - bar_len)}[/]"
        label = "Today" if i == 0 else d.strftime("%b %d")
        chart_lines.append(f" {label:<8}  {bar_str}  {mins}m")

    chart_text = "\n".join(chart_lines)
    console.print(
        Panel(chart_text, title="[bold]Last 14 Days[/]", border_style="blue")
    )

    # ------------------------------------------------------------------
    # Recent sessions table (last 10)
    # ------------------------------------------------------------------
    table = Table(
        "Date", "Duration", "Tag", "XP",
        border_style="dim",
        show_lines=False,
        header_style="bold dim",
    )
    for s in sessions_all[:10]:
        started = datetime.fromisoformat(s["started_at"]).astimezone()
        tag_str = s["tag"] or "—"
        table.add_row(
            started.strftime("%b %d %H:%M"),
            _duration_str(s["duration_seconds"]),
            tag_str,
            str(s["xp_awarded"]),
        )
    console.print(Panel(table, title="[bold]Recent Sessions[/]", border_style="dim"))

    # ------------------------------------------------------------------
    # Garden preview
    # ------------------------------------------------------------------
    nxt = garden.next_stage(stage)
    hours_left = garden.hours_to_next_stage(lifetime_hours)
    progress_line = (
        f"Next: [cyan]{nxt.label}[/] in {hours_left:.1f}h" if nxt and hours_left is not None
        else "[bold yellow]Maximum stage reached![/]"
    )
    garden_content = Text("\n".join(stage.art.splitlines()), style="green")
    garden_content.append_text(Text.from_markup(f"\n\n[bold green]{escape(stage.label)}[/]  ·  {progress_line}"))

    console.print(Panel(garden_content, title="[bold]Garden[/]", border_style="green"))
