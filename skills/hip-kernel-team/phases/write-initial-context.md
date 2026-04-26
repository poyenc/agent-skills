# Write Initial Context

Generate `.claude/teams/<team-name>/initial-context.md` from the
SessionStart hook output. Called by setup (step 7b) and resume
(step 3b).

## 1. Identify the SessionStart block

Find the `<system-reminder>` block whose first line starts with
`SessionStart`. This is the Claude Code hook system label for output
from session-start hooks.

**If not found:** Warn the user: "No SessionStart hook output found
— teammates will not receive session context." Write a stub file so
the hook has something to read:
```bash
echo "(No session context available)" > .claude/teams/<team-name>/initial-context.md
```
Then skip sections 2 and 3.

## 2. Write verbatim

1. Write the block verbatim to
   `.claude/teams/<team-name>/initial-context.md` using `Bash` with a
   heredoc:
   ```bash
   cat <<'INITIAL_CONTEXT_EOF' > .claude/teams/<team-name>/initial-context.md
   <paste entire block here>
   INITIAL_CONTEXT_EOF
   ```
2. Do NOT modify, condense, summarize, or reword. Every line, every
   heading, every path — exactly as received.
3. Do NOT add section headers, commentary, or formatting around the
   content.

**Why heredoc:** The Write tool's read-before-write guard blocks when
the file already exists from a prior session. `initial-context.md` is
fully generated content — the guard adds no value.

## 3. Verify structure

Spawn a subagent to report the written file's structure:

```
Agent({
  description: "Verify initial-context.md",
  subagent_type: "Explore",
  prompt: "Read .claude/teams/<team-name>/initial-context.md.
           Report all headings and section markers (lines
           starting with #, ===, or numbered steps like
           '1. '). Just list them, no commentary.
           Under 20 lines."
})
```

Compare the subagent's report against the headings/sections you see
in your SessionStart system-reminder. If any section is missing, the
copy was lossy — rewrite from the original SessionStart block.
