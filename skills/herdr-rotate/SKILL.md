---
name: herdr-rotate
description: >
  Rotate a running herdr coding agent (claude, pi, or codex): checkpoint its
  context to a handoff document, then exit and relaunch it in the SAME pane as a
  fresh session, replaying the user's exact launch command (model, effort, and
  every flag) recovered from the process argv. Use when the user says "rotate
  this agent", "refresh the agent's context", "restart the agent but keep its
  setup", "the agent's context is full", or when a context-watchdog recycles an
  agent. No-op outside herdr (HERDR_ENV != 1).
allowed-tools: Bash(*/scripts/herdr-rotate *), Bash(*/scripts/herdr-rotate-* *), Bash(herdr *)
---

# herdr-rotate

Rotate a running herdr agent in place: handoff -> exit -> relaunch (fresh
session, same pane/tab/workspace/name, same launch command).

## Usage

    herdr-rotate <name-or-pane> [--name N] [--model M] [--effort E] [--kickoff "<message>"] [--no-kickoff]

- `<name-or-pane>` — agent name or pane id (from `herdr agent list`).
- `--name N` — name for an unnamed agent on relaunch (default: derived `<kind>-<pane>`).
- `--model M` / `--effort E` — override launch model/effort (only if changed mid-session;
  pi model must be provider-qualified, e.g. `amd-gateway/gpt-5.6-terra`). Omitted -> replayed.
- `--kickoff "<msg>"` — custom first prompt (default: "continue from the handoff").
- `--no-kickoff` — relaunch without sending a resume prompt.

Run the dispatcher; it detects the kind and forwards to `herdr-rotate-<kind>`:

    skills/herdr-rotate/scripts/herdr-rotate <name-or-pane> [options]

## How it works

1. Resolve target -> kind, pane, name (derive if unnamed); validate name + overrides.
2. Capture launch argv from `herdr pane process-info` (NUL-safe; the only source for
   model/effort/flags — never the screen).
3. Handoff via a self-contained prompt (auto-triggers an installed handoff skill; stands
   alone otherwise); correlate the file via a per-rotation sentinel and verify on disk.
4. `/quit`; confirm the pane is free (`agent_not_found` + shell prompt).
5. `herdr agent start` same name+pane, replaying argv (with any override).
6. Poll the new agent to idle, verify argv element-by-element, then kickoff.

Nothing is parsed from header/footer/statusline, so it is robust to terminal width.
