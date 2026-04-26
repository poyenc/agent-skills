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

3b. **Regenerate initial context**: Overwrite
   `.claude/teams/<name>/initial-context.md` with your current session's
   pre-conversation context. Same format as setup step 7b. This ensures
   teammates get current CLAUDE.md rules, memory, hook output, and skill
   listings — not stale snapshots from the original session.

   **Tool note:** Use `Bash` with a heredoc (`cat <<'EOF' > path`) to
   write this file, not the Write tool. `initial-context.md` is fully
   generated content — Write's read-before-write guard adds no value
   here and will block when the file already exists from a prior session.

4. **Spawn team**: Read `${CLAUDE_SKILL_DIR}/phases/spawn.md` and follow
   it to re-spawn the team, assigning unfinished tasks to the appropriate
   members.
