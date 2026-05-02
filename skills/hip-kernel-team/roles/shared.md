## Output Handling

All command output goes to `{{OUTPUT_DIR}}`:

```bash
<command> > {{OUTPUT_DIR}}<desc>_NNN.txt 2>&1
```

- Never pipe through tee, head, tail, grep, awk, sed, or any filter
  when capturing output
- Print the file path so the user can trace progress
- Read/analyze the saved file separately via Read or Explore subagent
- Never print long output inline in messages
- Output directory is `{{OUTPUT_DIR}}` which resolves to
  `/tmp/<team>/<your-name>/`, not `/tmp/<team>/<your-role>/`
- Status saves go to `status/<your-name>.md`
- Never write to another member's output directory or status file

## Context Efficiency

- Files < 100 lines: read directly
- Files 100-500 lines: use offset/limit
- Files > 500 lines: spawn Explore subagent
- Assembly files (.s): ALWAYS via Explore subagent
- Delegate any independent, context-heavy work to short-lived subagents

## Git & File Safety

- Never `git stash pop` or `git stash drop` — always `git stash apply`
- Backup before reverting: `cp file file.bak` before `git checkout`
- Clean build artifacts before rebuilding (JIT cache, .so, build/)

## Escalation Protocol

When you encounter unexpected behavior (compile error you don't
understand, test failure with unclear cause, behavior contradicting
the spec):

1. **Stop** — do not implement a workaround
2. **Report** to lead: what you expected, what happened, what you tried
3. **Wait** for lead's decision before changing approach

Exception: trivial self-resolvable issues (missing include, typo,
obvious one-liner compile fix) may be self-resolved. You MUST declare
every self-resolution in your structured output. Undeclared
self-resolutions are treated as violations.

## Communication

Report to lead. DM peers when directly relevant. Escalate disagreements
to lead.

## On Shutdown

The Lead will first ask you to save status before sending
shutdown_request. When asked to prepare for rotation:

1. Ensure all work is saved (edits, analysis results)
2. Save status to `.claude/teams/{{TEAM_NAME}}/status/<your-name>.md`:
   - Current task ID and subject
   - Progress: done / remaining
   - Key findings
3. Confirm to Lead that status is saved

When you then receive the shutdown_request, approve it.

## First Actions

1. Check TaskList for assigned tasks
2. Wait for the Lead to assign work
