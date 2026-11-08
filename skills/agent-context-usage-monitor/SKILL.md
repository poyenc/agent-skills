---
name: agent-context-usage-monitor
description: Use whenever the lead needs to know how full the sched-* agents' context windows are, or whether any of them is due for rotation. Run the bundled script instead of eyeballing panes. Trigger on "monitor context", "monitor agent context", "monitor context usage", "check context", "context usage", "how full are the agents", "who needs rotating", "time to rotate", before handing a long task to a worker, when a worker's answers get vague or repetitive, and on any periodic team check. It reports each agent's context percent against its model's rotation threshold (Claude 55%, gpt-5.6-terra 45%, gpt-5.6-sol 25%). It is read-only: rotating is a separate step under agent-rotation-discipline.
---

# Check agent context usage against the rotation thresholds

Long-lived workers degrade as their context fills, and a rotation done too early or by guess has
cost this project hours before (see agent-rotation-discipline). The script gives the lead a
number to act on instead of a feeling: it reads each agent's pane, parses the status line, and
compares the context percent with the threshold for that agent's model.

## Run it

```bash
python3 -I .claude/skills/agent-context-usage-monitor/scripts/agent_context_usage.py
```

- Default scope: live herdr agents whose name starts with `sched-` (the only agents the lead may
  rotate, agent-rotation-discipline rule 6). `--names a,b` picks specific agents; `--prefix ''`
  lists every named agent for information only; `--json` gives machine-readable output.
- Output columns: agent, state, context percent of the window, the threshold for its model, token
  count, level, model.
- Level is `ROTATE` when the context percent is at or above the threshold, `ok` below it, and
  `unknown` when the status line or the model could not be parsed (so the agent's pane needs a
  manual look; do not treat unknown as ok).
- `--rotate-only` prints one line per agent at `ROTATE` (`ROTATE <name> state=<state> <percent>/<threshold>`),
  `UNKNOWN <name> state=<state> model=<model|unknown> context=<percent>/<window>|unknown` for an agent whose
  percent or model could not be parsed (pi hides the model in a narrow pane; no threshold is guessed; a parsed
  model missing from the threshold table prints its own name), and no line for an agent that is `ok`. Use it in a cron so
  the output itself says who to rotate and no judgement is needed.
- Exit status is 2 when any scanned agent is at `ROTATE`, 0 otherwise, 1 if herdr fails.

## When a row says ROTATE

Follow agent-rotation-discipline: rotate through the `herdr-kit:rotate` skill only, check the
agent's model against its role before and after, keep its harness and model, and never rotate an
agent whose level is `ok` on a hunch. The script never rotates and never messages an agent.

## What it depends on

- The status line that Claude Code and pi print at the bottom of the pane: `N%/1M` is context used
  over window, and `CH..%/..%` (cache hit) is ignored. If the status line format changes, rows turn
  `unknown`; fix the regular expressions in the script instead of guessing numbers.
- The thresholds in the script mirror agent-rotation-discipline rule 1. If the rule changes,
  change `THRESHOLDS` and `CLAUDE_THRESHOLD` in the script in the same edit.
- A one-shot run is enough for most questions. For a recurring check, use the
  poll-long-run-with-cron skill, only when the user asks for one, and delete the cron when it is no
  longer needed. Recommended interval: every 20 minutes (`*/20 * * * *`).
- A cron always runs `--rotate-only` (the default for recurring checks), never the full table. Its
  prompt must say: empty output means end the turn with no text, no tool call, no file write; act
  only on a `ROTATE` or `UNKNOWN` line. Cron prompt template:
  `Run python3 -I .claude/skills/agent-context-usage-monitor/scripts/agent_context_usage.py --rotate-only. Empty output: end the turn, write nothing, call nothing else. ROTATE <name>: rotate that idle agent with herdr-kit:rotate (never mid-run) and tell the user. UNKNOWN <name>: read its pane.`
