# context-watchdog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write `skills/context-watchdog/SKILL.md` — a self-contained skill that scans Claude Code panes in the current tmux window and reports context usage percentages, with optional periodic cron monitoring.

**Architecture:** Single `SKILL.md` file with subcommand dispatch (no argument = one-shot scan, `start` = cron monitor, `stop` = cancel). Scan logic is shared between one-shot and cron modes. No dependencies on other skills.

**Tech Stack:** Markdown skill instructions, tmux CLI, CronCreate/CronDelete tools.

## Global Constraints

- Self-contained: no references to `/rotate`, `/handoff`, or any other skill
- No threshold logic — report percentages only, never prescribe actions
- `CronCreate` only — never `sleep`-based polling
- Current tmux window only — never other windows or sessions
- Default parse pattern: `context:\s*(\d+)%` (case-insensitive substring match)
- On parse failure: ask user for their format, store for session, never assume

---

### Task 1: Write SKILL.md

**Files:**
- Rewrite: `skills/context-watchdog/SKILL.md`

**Interfaces:**
- Produces: a skill invocable as `/context-watchdog`, `/context-watchdog start`, `/context-watchdog stop`

- [ ] **Step 1: Write the frontmatter and description**

The description must be specific enough to trigger reliably. Write:

```markdown
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
```

- [ ] **Step 2: Write the Mode Dispatch section**

```markdown
# Context Watchdog

Scan Claude Code panes in the current tmux window and report their context
usage percentage. Pure observability — no threshold, no prescribed actions.

## Mode Dispatch

Parse `$ARGUMENTS`:

- **Empty / no argument** → one-shot scan (read-only, safe to run anytime)
- **`start`** → setup and start cron monitor
- **`stop`** → cancel active cron job
```

- [ ] **Step 3: Write the Scan Procedure section**

This is the core logic shared by both one-shot and cron modes:

```markdown
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
```

- [ ] **Step 4: Write the One-Shot section**

```markdown
## One-Shot Mode (no argument)

Run the Scan Procedure once and exit. No cron is created. Safe to run at
any time to verify parsing works before starting the monitor.
```

- [ ] **Step 5: Write the Monitor Mode (start) section**

```markdown
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
   - `prompt`: the full Scan Procedure instructions (self-contained —
     include the tmux commands, parse pattern, and output format verbatim
     so the cron agent needs no external context)
4. Print the cron job ID and confirm:

```
Context watchdog started.
  Interval : every <N> minutes
  Cron ID  : <id>

Run `/context-watchdog stop` to cancel.
```

Never use `sleep` or background Bash loops. Only `CronCreate`.
```

- [ ] **Step 6: Write the Stop section**

```markdown
## Stop Mode — stop

1. If a cron ID is available in context (from the `start` output), use it.
2. Otherwise ask: "What is the cron job ID? (Run `CronList` to find it.)"
3. Call `CronDelete` with that ID.
4. Confirm:

```
Context watchdog stopped.
```
```

- [ ] **Step 7: Self-review the complete SKILL.md**

Check:
- All three modes are present and self-contained
- Scan Procedure is complete (tmux check → pane detect → parse → print)
- No references to `/rotate`, `/handoff`, or any other skill
- No threshold logic anywhere
- `CronCreate` prompt in monitor mode is fully self-contained (no external file references)
- Parse failure path asks user and stores custom pattern
- Output format matches the spec exactly

Fix any issues found inline.

- [ ] **Step 8: Commit**

```bash
git add skills/context-watchdog/SKILL.md
git commit -m "feat: add context-watchdog skill"
```

Expected: 1 file changed (or modified if draft existed).
