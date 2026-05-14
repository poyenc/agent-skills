# Spawn Team

After config is saved (new or resumed):

## 1. Create the team

```
TeamCreate({ team_name: "<team-name>" })
```

## 2. Create output directories

```bash
mkdir -p /tmp/<team-name>/<member-name>/ # for each permanent member, using their NAME not role
```

On-demand roles get their directories created at spawn time by the Lead.

## 3. Create initial tasks

For resumed teams, carry forward unfinished tasks from the prior
session. For new teams, skip — direction comes from the user in step 9.

## 4. Read role templates

Read each needed role file from `${CLAUDE_SKILL_DIR}/roles/<role>.md`

## 5. Read shared rules

Read `${CLAUDE_SKILL_DIR}/roles/shared.md` — this content is appended
to every member's prompt after their role template.

## 6. Prepare inline state summary

For each member being spawned, read `{{STATUS_FILE}}` and check if
`.claude/teams/<team-name>/status/<member-name>.md` exists. Compose a compact
summary (under 10 lines) of: current state, recent results, active
tasks, key findings, and any rotation handoff notes. If no status files
exist, use: `"Fresh team -- no prior state. Wait for task assignment."`

## 7. Fill placeholders

Fill placeholders in each template with values from config:

| Placeholder | Source |
|-------------|--------|
| `{{GOAL}}` | Config Goal section |
| `{{CONSTRAINTS}}` | Config Constraints section |
| `{{STATUS_FILE}}` | Recall path or `.claude/teams/<name>/status.md` |
| `{{WORKFLOWS}}` | Config Workflows section |
| `{{CURRENT_STATE}}` | Inline state summary prepared in step 6 |
| `{{KEY_FILES}}` | Config Key Files section |
| `{{TEAM_MEMBERS}}` | Roster of teammate names and roles |
| `{{TEAM_MEMBERS_COUNT}}` | Number of team members (e.g., "4") |
| `{{ENVIRONMENT}}` | Config Environment section |
| `{{OUTPUT_DIR}}` | `/tmp/<team-name>/<member-name>/` |
| `{{EVALUATION_CRITERIA}}` | Config Evaluation Criteria section |
| `{{TEAM_NAME}}` | Team name |
| `{{KNOWLEDGE_PATH}}` | Recall path or `.claude/teams/<name>/knowledge.md` |
| `{{MEMORY_PATH}}` | Memory directory path from config (only when `sync_to_memory` is true) |

## 8. Spawn member agents

Spawn each member (not Lead — Lead is you, the main conversation).

Read the `Model` column from the config Roles table for each member.
If `(parent)` or empty, omit the `model` parameter.

```
Agent({
  prompt: <filled role template + shared rules>,
  team_name: "<team-name>",
  name: "<member-name>",
  subagent_type: "general-purpose",
  model: "<model from config Roles table, omit if '(parent)'>"
})
```

## 9. Ask user for direction

Do NOT auto-create investigation tasks. Instead, ask the user:

> "Team is ready — <N> members standing by (<list names and roles>).
> What should we work on first?"

Wait for the user's answer. Then decompose into tasks using the
appropriate pipeline template from `decompose.md` and assign.

## 10. Begin operating as Lead

Follow the Lead instructions in `${CLAUDE_SKILL_DIR}/roles/lead.md`
for the rest of the session.
