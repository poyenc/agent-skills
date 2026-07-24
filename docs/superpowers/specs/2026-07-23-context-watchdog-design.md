# context-watchdog skill design

**Date:** 2026-07-23
**Status:** approved

## Overview

A self-contained, general-purpose skill that periodically scans all Claude
Code panes in the current tmux window and reports their context usage as a
percentage. Pure observability — no threshold logic, no prescribed actions,
no dependencies on other skills. The main agent applies whatever decision
logic the user instructed it with.

## Commands

```
/context-watchdog           → one-shot scan
/context-watchdog start     → start periodic cron monitor
/context-watchdog stop      → cancel active cron
```

### One-shot (default, no argument)

Scan all Claude panes in the current tmux window and print a summary table.
Safe, read-only, idempotent. Useful as a dry-run to verify parsing works
before starting the monitor.

### start

Ask the user for a check interval (default: 5 minutes), then start a
`CronCreate` job that runs the scan on every tick. Print the cron job ID so
the user can cancel it later. The job runs until explicitly stopped — no
auto-cancel, no threshold.

### stop

Cancel the active cron job via `CronDelete`. Ask the user for the cron ID
if not available in context (they can also run `CronList` to find it).

## Scan Logic

### 1. tmux check

Run `tmux info 2>/dev/null`. If it fails, print one line:

```
[context-watchdog] Not in a tmux session.
```

and exit. No-op — do not error.

### 2. Pane detection

```bash
tmux list-panes -F '#{pane_id} #{pane_title} #{pane_current_command}'
```

Filter to panes where `pane_current_command` is `claude`. Scope to the
**current window only** — never other windows or sessions.

If no Claude panes found, print:

```
[context-watchdog] No Claude panes in this window.
```

and exit.

### 3. Context parsing

For each Claude pane, capture the last 8 lines:

```bash
tmux capture-pane -p -t <pane_id> -S -8
```

Search for the pattern `context:\s*(\d+)%` (case-insensitive substring match).
Extract the integer N as the context percentage.

**On parse failure for any pane:** stop and ask the user:

> "Could not parse context from pane `<pane_id>` (`<title>`). What format does
> your status bar use? (e.g. `ctx: 45%`, `used: 45%`)"

Store the user-provided pattern for the remainder of the session and retry.
Show `?%` for any pane that still fails after the custom pattern is tried.

### 4. Output format

```
[context-watchdog] HH:MM — N Claude pane(s) in window <id>:
  PANE   TITLE            CONTEXT
  %207   Implementer        54%
  %12    Implementer        45%
  %21    main               10%
```

- Timestamp from `date +%H:%M`
- Pane ID is always shown — it is the unambiguous identity (titles can collide)
- Title truncated to ~16 chars if long
- `?%` for any pane where parsing failed

## Design Decisions

**No threshold.** The skill reports only. All decision logic (when to rotate,
when to handoff) lives in the main agent's instructions or the user's prompt.
This keeps the skill composable — the user glues it with other skills as they
see fit.

**Current window only.** The user's agents are typically co-located in one
tmux window. Scanning other windows would surface unrelated sessions.

**Pane ID as identity.** Pane titles can collide (multiple agents with the
same role name). Pane ID (`%207`) is always unique and is what the user
passes to other tools like `/rotate`.

**`context: N%` as the default parse pattern.** This is the format Claude
Code's built-in status bar uses. On failure, ask rather than assume — the
user's environment may differ.

**`CronCreate` only — never `sleep`.** Polling via `sleep` in Bash blocks the
agent. `CronCreate` fires asynchronously and keeps the main thread free.

**No references to other skills.** `context-watchdog` does not mention
`/rotate`, `/handoff`, or any other skill. It is a standalone reporter.

## Non-Goals

- Threshold-based alerting
- Auto-cancelling on any condition
- Prescribing what action to take
- Scanning panes outside the current window
- Tracking token counts or assuming context window size
- Depending on hip-kernel-team or any other skill
