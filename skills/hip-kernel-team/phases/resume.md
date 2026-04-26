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

3b. **Stop stale agents**: For each non-lead role in the config Roles
    table, send a `shutdown_request` via `SendMessage` to the role name.
    This terminates agents left over from prior sessions that weren't
    cleanly shut down, releasing their names. Ignore delivery failures
    (the agent may not exist). Wait briefly for responses before
    proceeding.

4. **Spawn team**: Read `${CLAUDE_SKILL_DIR}/phases/spawn.md` and follow
   it to re-spawn the team, assigning unfinished tasks to the appropriate
   members.
