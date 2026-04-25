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

## Communication

Report to lead. DM peers when directly relevant. Escalate disagreements
to lead.

## On Shutdown

The Lead will first ask you to save status before sending
shutdown_request. When asked to prepare for rotation:

1. Ensure all work is saved (edits, analysis results)
2. Save status to `.claude/teams/{{TEAM_NAME}}/status/<role>.md`:
   - Current task ID and subject
   - Progress: done / remaining
   - Key findings
3. Confirm to Lead that status is saved

When you then receive the shutdown_request, approve it.

## First Actions

1. Check TaskList for assigned tasks
2. Wait for the Lead to assign work
