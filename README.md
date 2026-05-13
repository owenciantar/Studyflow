# studyflow

A CLI flowtime study timer with XP, streaks, and a growing ASCII garden. Runs entirely in the terminal.

## Install

```bash
# Use Python 3.13 (recommended — avoids a Homebrew Python 3.14 .pth file bug)
python3.13 -m venv .venv
.venv/bin/pip install -e .
```

Then run via `.venv/bin/studyflow`, or activate the venv first:

```bash
source .venv/bin/activate
studyflow start
```

Requires Python 3.11+. Dependencies (`rich`, `typer`, `platformdirs`) are installed automatically.

> **Note:** Homebrew Python 3.14 has a macOS `UF_HIDDEN` flag issue that prevents editable installs
> from being found. Use Python 3.13 from `python.org` or pyenv to avoid this.

## Commands

```
studyflow start [--tag TAG]   Start a session. s = save, q = quit without XP.
studyflow stats               Full dashboard: XP, streaks, chart, garden.
studyflow garden              Show current garden stage.
studyflow goal set MINUTES    Set daily goal (default: 120 min).
studyflow goal show           Print current goal.
studyflow history [--days N]  List past sessions (default: last 30 days).
studyflow reset --confirm     Wipe all data.
```

## Mechanics

**Flowtime** — no fixed intervals. Start when ready, stop when done. Sessions under 5 minutes are not recorded.

**XP** — 1 XP/minute, +20% bonus for sessions ≥ 50 min, +50% for ≥ 90 min.

**Levels** — Level N requires `N×(N+1)×50` cumulative XP (100 for Level 1, 300 for Level 2, …).

**Streaks** — consecutive days meeting your daily goal. A grace day (one miss per 7-day window) kicks in once your streak reaches 7 days.

**Garden** — ASCII plant that grows as your lifetime hours accumulate:
Seed (0h) → Sprout (1h) → Seedling (5h) → Sapling (15h) → Young Tree (40h) → Mature Tree (100h) → Flowering Tree (250h) → Ancient Tree (500h)

**Data** — stored in a SQLite database at:
- macOS: `~/Library/Application Support/studyflow/studyflow.db`
- Linux: `~/.local/share/studyflow/studyflow.db`
