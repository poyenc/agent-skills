# Spawn Team

After config is saved (new or resumed):

## 1. Create the team

```
TeamCreate({ team_name: "<team-name>" })
```

## 2. Create output directories

```bash
mkdir -p /tmp/<team-name>/<role>/ # for each member role
```

## 3. Create initial tasks

If no specific tasks exist yet, create an investigation task:
"Investigate: understand current state and propose initial task list"

## 4. Read role templates

Read each needed role file from `${CLAUDE_SKILL_DIR}/roles/<role>.md`

## 5. Prepare inline state summary

For each member being spawned, read `{{STATUS_FILE}}` and check if
`.claude/teams/<team-name>/status/<role>.md` exists. Compose a compact
summary (under 10 lines) of: current state, recent results, active
tasks, key findings, and any rotation handoff notes. If no status files
exist, use: `"Fresh team -- no prior state. Wait for task assignment."`

## 6. Fill placeholders

Fill placeholders in each template with values from config:

| Placeholder | Source |
|-------------|--------|
| `{{GOAL}}` | Config Goal section |
| `{{CONSTRAINTS}}` | Config Constraints section |
| `{{STATUS_FILE}}` | Recall path or `.claude/teams/<name>/status.md` |
| `{{KNOWLEDGE_FILE}}` | Recall path or `.claude/teams/<name>/knowledge.md` |
| `{{WORKFLOWS}}` | Config Workflows section |
| `{{CURRENT_STATE}}` | Inline state summary prepared in step 5 |
| `{{KEY_FILES}}` | Config Key Files section |
| `{{TEAM_MEMBERS}}` | Roster of teammate names and roles |
| `{{TEAM_MEMBERS_COUNT}}` | Number of team members (e.g., "4") |
| `{{ENVIRONMENT}}` | Config Environment section |
| `{{OUTPUT_DIR}}` | `/tmp/<team-name>/<role>/` |
| `{{EVALUATION_CRITERIA}}` | Config Evaluation Criteria section |
| `{{TEAM_NAME}}` | Team name |

## 7. Spawn member agents

Spawn each member (not Lead — Lead is you, the main conversation):

```
Agent({
  prompt: <filled role template>,
  team_name: "<team-name>",
  name: "<member-name>",
  subagent_type: "general-purpose"
})
```

## 8. Assign initial tasks

Assign tasks via TaskUpdate.

## 9. Begin operating as Lead

Follow the Lead instructions in `${CLAUDE_SKILL_DIR}/roles/lead.md`
for the rest of the session.
