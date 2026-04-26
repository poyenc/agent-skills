# Resume Team

`/hip-kernel-team load <name>`

## Steps

1. **Read config**: Read `.claude/teams/<name>/config.md`

2. **Read status files**: Read all status files:
   - `.claude/teams/<name>/status/*.md` (per-member rotation status)
   - If recall is enabled in config: read the recall status.md at the
     path specified in the Recall section

3. **Print resumption summary**: Print:
   "Resuming team **<name>**. State: <summary of where things left off>"

   Include: last completed task, any in-progress tasks, team composition,
   key recent results.

3b. **Regenerate initial context**: Copy your SessionStart hook output
   (the `<system-reminder>` block labeled "SessionStart" that contains
   hook-injected directives, project config, user profile, etc.)
   **exactly as received** into
   `.claude/teams/<team-name>/initial-context.md`.

   Rules:
   - **Do NOT modify, condense, summarize, or reword.** Copy verbatim.
   - **Do NOT include** CLAUDE.md rules, skill listings, currentDate,
     or gitStatus — the system auto-injects these into subagents.
   - **Do NOT add** section headers, commentary, or formatting around
     the hook output. Paste it as-is.

   **Tool note:** Use `Bash` with a heredoc (`cat <<'EOF' > path`) to
   write this file, not the Write tool. `initial-context.md` is fully
   generated content — Write's read-before-write guard adds no value
   here and will block when the file already exists from a prior session.

3c. **Stop stale agents**: For each non-lead role in the config Roles
    table, send a `shutdown_request` via `SendMessage` to the role name.
    This terminates agents left over from prior sessions that weren't
    cleanly shut down, releasing their names. Ignore delivery failures
    (the agent may not exist). Wait briefly for responses before
    proceeding.

4. **Spawn team**: Read `${CLAUDE_SKILL_DIR}/phases/spawn.md` and follow
   it to re-spawn the team, assigning unfinished tasks to the appropriate
   members.
