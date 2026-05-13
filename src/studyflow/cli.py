"""Typer CLI commands for studyflow."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from studyflow import db, garden

app = typer.Typer(
    name="studyflow",
    help="Flowtime study timer with XP, streaks, and a growing garden.",
    add_completion=False,
    rich_markup_mode="rich",
)

console = Console()


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------

@app.command()
def start(
    tag: Annotated[
        Optional[str],
        typer.Option("--tag", "-t", help="Label this session (e.g. 'calculus')."),
    ] = None,
) -> None:
    """Start a flowtime study session. Press [bold]s[/] to save, [bold]q[/] to quit."""
    from studyflow.timer import run_session
    run_session(tag=tag)


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

@app.command()
def stats() -> None:
    """Show the full stats dashboard: XP, streaks, history, garden."""
    from studyflow.stats import render_dashboard
    db.init_db()
    render_dashboard(console)


# ---------------------------------------------------------------------------
# garden
# ---------------------------------------------------------------------------

@app.command(name="garden")
def show_garden() -> None:
    """Display current garden stage and progress to the next."""
    db.init_db()
    lifetime_hours = db.get_lifetime_hours()
    stage = garden.stage_for_hours(lifetime_hours)
    nxt = garden.next_stage(stage)
    hours_left = garden.hours_to_next_stage(lifetime_hours)

    markup = "\n".join(f"[green]{escape(line)}[/]" for line in stage.art.splitlines())
    markup += f"\n\n[bold green]{stage.label}[/]\n[dim]Lifetime hours: {lifetime_hours:.1f}h[/]\n"
    if nxt and hours_left is not None:
        markup += f"Next stage [cyan]{nxt.label}[/] in {hours_left:.1f}h"
    else:
        markup += "[bold yellow]You have reached the final garden stage![/]"

    console.print(Panel(markup, title="[bold green]Garden[/]", border_style="green"))


# ---------------------------------------------------------------------------
# goal
# ---------------------------------------------------------------------------

goal_app = typer.Typer(help="Manage your daily study goal.")
app.add_typer(goal_app, name="goal")


@goal_app.command("set")
def goal_set(
    minutes: Annotated[int, typer.Argument(help="Daily goal in minutes.")],
) -> None:
    """Set your daily study goal."""
    if minutes <= 0:
        console.print("[red]Goal must be a positive number of minutes.[/]")
        raise typer.Exit(1)
    db.init_db()
    db.set_state("daily_goal_minutes", str(minutes))
    h = minutes // 60
    m = minutes % 60
    label = f"{h}h {m:02d}m" if h else f"{m}m"
    console.print(f"[green]Daily goal set to {label} ({minutes} min).[/]")


@goal_app.command("show")
def goal_show() -> None:
    """Show the current daily study goal."""
    db.init_db()
    minutes = int(db.get_state("daily_goal_minutes", "120"))
    h = minutes // 60
    m = minutes % 60
    label = f"{h}h {m:02d}m" if h else f"{m}m"
    console.print(f"Daily goal: [bold cyan]{label}[/] ({minutes} min)")


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------

@app.command()
def history(
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="How many days of history to show."),
    ] = 30,
) -> None:
    """List past study sessions."""
    from rich.table import Table

    db.init_db()
    sessions = db.get_sessions(days=days)

    if not sessions:
        console.print(f"[dim]No sessions in the last {days} days.[/]")
        return

    table = Table(
        "#", "Started", "Duration", "Tag", "XP",
        border_style="dim",
        show_lines=False,
        header_style="bold",
    )
    for i, s in enumerate(sessions, 1):
        started = datetime.fromisoformat(s["started_at"]).astimezone()
        secs = s["duration_seconds"]
        h, m = secs // 3600, (secs % 3600) // 60
        dur = f"{h}h {m:02d}m" if h else f"{m}m"
        table.add_row(
            str(i),
            started.strftime("%Y-%m-%d %H:%M"),
            dur,
            s["tag"] or "—",
            str(s["xp_awarded"]),
        )

    console.print(table)
    console.print(f"[dim]{len(sessions)} session(s) in the last {days} days[/]")


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------

@app.command()
def reset(
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Required to actually wipe data."),
    ] = False,
) -> None:
    """Wipe ALL studyflow data. Irreversible — requires --confirm."""
    if not confirm:
        console.print(
            "[red]This will delete all sessions, XP, and progress.[/]\n"
            "Pass [bold]--confirm[/] to proceed."
        )
        raise typer.Exit(1)

    import sqlite3
    db.init_db()
    with db.get_conn() as conn:
        conn.execute("DELETE FROM sessions")
        conn.execute("DELETE FROM unlocks")
        conn.execute("DELETE FROM state")

    console.print("[yellow]All data wiped.[/]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app()
