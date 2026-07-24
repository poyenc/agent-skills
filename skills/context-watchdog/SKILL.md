---
name: context-watchdog
description: >
  Monitor Claude Code agent context usage across tmux panes. Scans all
  Claude panes in the current tmux window and reports their context
  percentage. Use when the user says "context-watchdog", "monitor context
  usage", "watch agent context", "check how full my agents are", "scan
  pane context", "start context monitoring", or when running a multi-agent
  session and wanting periodic context reports. Also trigger when the user
  says "how full are my agents", "which panes are near context limit", or
  "set up context monitoring for my team".
user-invocable: true
argument-hint: "[start | stop]"
---

# Context Watchdog

Scan Claude Code panes in the current tmux window and report their context
usage percentage. Pure observability — no threshold, no prescribed actions.

## Mode Dispatch

Parse `$ARGUMENTS`:

- **Empty / no argument** → one-shot scan (read-only, safe to run anytime)
- **`start`** → setup and start cron monitor
- **`stop`** → cancel active cron job

## Scan Procedure

### 1. tmux check

```bash
tmux info 2>/dev/null
```

If the command fails or returns nothing, print exactly:

```
[context-watchdog] Not in a tmux session.
```

and stop. This is a no-op, not an error.

### 2. Detect Claude panes in current window

```bash
tmux list-panes -F '#{pane_id} #{pane_title} #{pane_current_command}'
```

Keep only lines where the third field is `claude`. These are the panes
to scan. Do not scan other windows or sessions.

Note: this detects Claude Code launched directly. If Claude is running inside
a wrapper (Node, Electron, or a shell script), `pane_current_command` may show
the wrapper name instead. Use the one-shot mode to verify detection works in
your environment before starting the monitor.

If no Claude panes found, print:

```
[context-watchdog] No Claude panes in this window.
```

and stop.

### 3. Parse context percentage from each pane

For each Claude pane, run:

```bash
tmux capture-pane -p -t <pane_id> -S -8
```

Search the output for the pattern `context:\s*(\d+)%`
(case-insensitive). Extract the integer as the context percentage.

If the pattern does not match for any pane, stop and ask the user:

> "Could not parse context from pane `<pane_id>` (`<title>`).
> What format does your status bar show? (e.g. `ctx: 45%`, `used: 45%`)"

Store the custom pattern the user provides and retry all failed panes
with it. Any pane still failing after the custom pattern shows `?%`.

(This interactive fallback applies to one-shot mode only. In cron mode, follow the embedded cron prompt's step 3 instead.)

### 4. Print summary table

```
[context-watchdog] HH:MM — N Claude pane(s) in window <window_id>:
  PANE   TITLE            CONTEXT
  %207   Implementer        54%
  %12    Implementer        45%
  %21    main               10%
```

- Get timestamp with `date +%H:%M`
- Always show pane ID — it is the unambiguous identity (titles can collide)
- Truncate title to 16 characters if longer
- Show `?%` for any pane where parsing failed
- Get window ID with `tmux display-message -p '#{window_id}'`

## One-Shot Mode (no argument)

Run the Scan Procedure once and exit. No cron is created. Safe to run at
any time to verify parsing works before starting the monitor.

## Monitor Mode — start

1. Ask the user: "How often should I scan? [default: 5 minutes]"
2. Map the answer to a cron expression:
   - 1 minute → `* * * * *`
   - 5 minutes → `*/5 * * * *`
   - 10 minutes → `*/10 * * * *`
   - 15 minutes → `*/15 * * * *`
   - 30 minutes → `*/30 * * * *`
   - 1 hour → `0 * * * *`
   - For other values, derive the cron expression directly.
3. Call `CronCreate` with:
   - `cron`: the expression above
   - `recurring`: true
   - `prompt`: the full Scan Procedure instructions below (self-contained)
4. Print the cron job ID and confirm:

```
Context watchdog started.
  Interval : every <N> minutes
  Cron ID  : <id>

Run `/context-watchdog stop` to cancel.
Note: cron jobs expire after 7 days — re-run `/context-watchdog start` to renew.
```

Never use `sleep` or background Bash loops. Only `CronCreate`.

### CronCreate prompt (embed this verbatim in the cron prompt field)

```
Run the following context scan procedure:

1. Run: tmux info 2>/dev/null
   If the command fails or returns nothing, print exactly:
     [context-watchdog] Not in a tmux session.
   and stop.

2. Run: tmux list-panes -F '#{pane_id} #{pane_title} #{pane_current_command}'
   Keep only lines where the third field is exactly "claude".
   If no such lines exist, print:
     [context-watchdog] No Claude panes in this window.
   and stop.

3. For each Claude pane (identified by pane_id from step 2), run:
     tmux capture-pane -p -t <pane_id> -S -8
   Search the output (case-insensitive) for the regex pattern: context:\s*(\d+)%
   Extract the integer match as the context percentage for that pane.
   If the pattern does not match, mark that pane as "?%" and add a note
   in the output: "(run /context-watchdog with no args to diagnose parse failures)"

4. Get the current timestamp with: date +%H:%M
   Get the window ID with: tmux display-message -p '#{window_id}'
   Print a summary table in exactly this format:
     [context-watchdog] HH:MM — N Claude pane(s) in window <window_id>:
       PANE   TITLE            CONTEXT
       %207   Implementer        54%
       %12    Implementer        45%
       %21    main               10%
   (replace with actual pane IDs, titles, and percentages from the scan)
   Rules:
   - Always show the pane ID (unambiguous identity)
   - Truncate title to 16 characters if longer
   - Show ?% for any pane where parsing failed
```

## Stop Mode — stop

1. If a cron ID is available in context (from the `start` output), use it.
2. Otherwise: run `CronList` to find the active cron job ID, then use it.
3. Call `CronDelete` with that ID.
4. Confirm:

```
Context watchdog stopped.
```
