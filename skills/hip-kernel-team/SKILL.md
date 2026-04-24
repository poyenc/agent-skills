---
name: hip-kernel-team
description: >
  Launch and manage a multi-agent team for HIP/GPU kernel development,
  debugging, and optimization. Configurable roles (Lead, Implementer,
  Profiler, Researcher) with optional recall-plugin integration and
  long-running context rotation. Use this skill whenever the user wants to:
  start a kernel optimization team, launch agents to work on a HIP kernel,
  create a dev team for GPU kernel work, set up a multi-agent workflow for
  kernel performance tuning, or resume a previously saved team config.
  Also trigger when the user says things like "start a team to optimize
  kernel X", "launch agents for my HIP kernel", "hip-kernel-team load",
  "resume my kernel team", or "set up a dev team for this GPU kernel".
user-invocable: true
argument-hint: "[load <name> | list | update <name>]"
---

# HIP Kernel Team

Launch a multi-agent team for HIP kernel development, debugging, and
optimization. The skill defines **HOW** the team operates (roles,
communication, lifecycle, context management). The user defines **WHAT**
to do (goal, constraints, tasks).

## Quick Reference

| Command | Effect |
|---------|--------|
| `/hip-kernel-team` | Conversational setup — create a new team |
| `/hip-kernel-team load <name>` | Re-launch a team from saved config |
| `/hip-kernel-team list` | Show all saved team configs |
| `/hip-kernel-team update <name>` | Modify an existing config |

## Mode Dispatch

Parse `$ARGUMENTS`:

- **Empty or unrecognized** → [New Team Setup](#new-team-setup)
- **`load <name>`** → [Resume Team](#resume-team)
- **`list`** → [List Teams](#list-teams)
- **`update <name>`** → [Update Config](#update-config)

---

## New Team Setup

Walk the user through these steps **one question at a time**. Use
`AskUserQuestion` when choices are discrete, plain text when open-ended.

### Step 1: Goal

Ask: "What is the goal for this team?"

The user describes the goal in natural language. This becomes the
`## Goal` section of the config.

### Step 2: Role Recommendation

Based on the goal, recommend a team composition from the role catalog.
Present your recommendation and reasoning, then ask the user to confirm
or override.

**Role catalog** (each member has a unique role, no duplicates):

| Role | Core Function |
|------|--------------|
| **Lead** | Task list management, team coordination, keep/revert decisions, member rotation. Runs in the main conversation (not spawned). Always present. |
| **Implementer** | Code editing (HIP/C++/Python), build, correctness tests, PR feedback handling |
| **Profiler** | Assembly analysis, HW counter profiling (rocprofv3), benchmarking, ISA comparison |
| **Researcher** | External code/paper analysis, compiler internals investigation, ISA docs |

**Recommendation table:**

| Goal Pattern | Recommended Roles | Why |
|-------------|------------------|-----|
| Optimize existing kernel | Lead + Implementer + Profiler | Need assembly analysis + benchmarking |
| Debug correctness issue | Lead + Implementer | Tight build-test loop |
| Port algorithm from paper/reference | Lead + Implementer + Researcher | Need external research |
| Full development (new kernel) | Lead + Implementer + Profiler + Researcher | All lifecycle phases |
| Investigate perf regression | Lead + Profiler + Researcher | Analysis-heavy, minimal code changes |

**Soft warnings** (don't block, just inform):
- Profiler without Implementer: "Who will implement the findings?"
- Researcher without Implementer: "Who will write the code?"
- Only Lead: "Lead can absorb other roles but the team will be slower."

### Step 3: Constraints

Ask: "Any constraints? (compiler version, hardware target, compatibility
requirements, or 'none')"

### Step 4: Recall Detection

Auto-detect the recall plugin:

```bash
ls ~/.local/share/claude/recall/ 2>/dev/null
```

- **Found**: detect project name from git remote or directory name, detect
  branch from `git branch --show-current`. Ask user to confirm:
  "Recall detected (project: X, branch: Y). Use this? If yes, what task
  name should I use?"
- **Not found**: "No recall plugin detected. I'll use project-local files
  at `.claude/teams/<name>/` for status tracking."

### Step 5: Key Files

Ask: "Any key reference files the team should know about? (source files,
reference implementations, or 'none — team will discover')"

### Step 6: Workflows

Ask: "Build/test/bench commands? (or 'team will figure out')"

If recall is present and a workflows.md exists for the detected task,
offer to auto-populate: "Found existing workflows in recall. Use those?"

### Step 7: Team Name & Confirmation

Generate a short kebab-case team name from the goal (e.g.,
`ck-fmha-v3-opt`). Print a full summary of the config. Ask user to
confirm.

### Step 8: Save & Spawn

1. Save config to `.claude/teams/<team-name>/config.md`
   (see [Config Format](#config-format))
2. Proceed to [Spawn Team](#spawn-team)

---

## Resume Team

`/hip-kernel-team load <name>`

1. Read `.claude/teams/<name>/config.md`
2. Read all status files: `.claude/teams/<name>/status/*.md`
   and/or recall status.md if recall is enabled
3. Print: "Resuming team **<name>**. State: <summary of where things
   left off>"
4. Proceed to [Spawn Team](#spawn-team), assigning unfinished tasks

---

## List Teams

`/hip-kernel-team list`

1. Glob `.claude/teams/*/config.md`
2. For each, extract name, goal (first 80 chars), roles, created date
   from frontmatter
3. Print a table

---

## Update Config

`/hip-kernel-team update <name>`

1. Read `.claude/teams/<name>/config.md`
2. Ask: "What would you like to change?"
3. Update the config file based on user input

---

## Config Format

Saved to `.claude/teams/<team-name>/config.md`. Human-readable markdown
with YAML frontmatter. The user can edit this file directly.

```markdown
---
template: hip-kernel-team
version: "1.0"
name: <team-name>
created: <YYYY-MM-DD>
---

# Team: <team-name>

## Goal

<Goal description>

## Constraints

- <constraint>

## Roles

| Name | Role | Notes |
|------|------|-------|
| lead | Lead | Coordinator (main conversation) |
| <name> | <Role> | <notes> |

## Environment

- Container: `<name>`
- Workspace: `<path>`

## Recall

- Enabled: true/false
- Project: <name>
- Branch: <branch>
- Task: <task>

## Key Files

- `<path>`

## Workflows

### Build
<build command>

### Test
<test command>

### Benchmark
<benchmark command>

## Context Management

- Member rotation threshold: 60%
- Output directory: /tmp/<team-name>/
- Delegate reads above: 500 lines

## Evaluation Criteria

- <criteria defined by Lead based on goal>
```

---

## Spawn Team

After config is saved (new or resumed):

1. **Create the team**:
   ```
   TeamCreate({ team_name: "<team-name>" })
   ```

2. **Create output directories**:
   ```bash
   mkdir -p /tmp/<team-name>/<role>/ # for each member role
   ```

3. **Create initial tasks**: If no specific tasks exist yet, create an
   investigation task: "Investigate: understand current state and propose
   initial task list"

4. **Read role templates**: Read each needed role file from
   `${CLAUDE_SKILL_DIR}/roles/<role>.md`

5. **Fill placeholders** in each template with values from config:

   | Placeholder | Source |
   |-------------|--------|
   | `{{GOAL}}` | Config Goal section |
   | `{{CONSTRAINTS}}` | Config Constraints section |
   | `{{STATUS_FILE}}` | Recall path or `.claude/teams/<name>/status.md` |
   | `{{KNOWLEDGE_FILE}}` | Recall path or `.claude/teams/<name>/knowledge.md` |
   | `{{WORKFLOWS}}` | Config Workflows section |
   | `{{KEY_FILES}}` | Config Key Files section |
   | `{{TEAM_MEMBERS}}` | Roster of teammate names and roles |
   | `{{COMMUNICATION_RULES}}` | Generated from role pairs present |
   | `{{ENVIRONMENT}}` | Config Environment section |
   | `{{OUTPUT_DIR}}` | `/tmp/<team-name>/<role>/` |
   | `{{EVALUATION_CRITERIA}}` | Config Evaluation Criteria section |
   | `{{TEAM_NAME}}` | Team name |

6. **Generate communication rules** from the roles present. Only include
   pairs where both roles exist on the team:

   | From | To | When |
   |------|----|------|
   | Lead | Any | Task assignment, decisions, feedback |
   | Any | Lead | Reports, proposals, questions, escalations |
   | Implementer | Profiler | "Check assembly/perf after my change" |
   | Profiler | Implementer | "Analysis shows X, suggest Y at line Z" |
   | Researcher | Implementer | "Reference does X this way" |
   | Researcher | Profiler | "Reference has N instructions, compare" |
   | Profiler | Researcher | "How does reference handle X?" |
   | Implementer | Researcher | "How does reference implement X?" |

   **Escalation**: If members disagree, either escalates to Lead. Lead
   decides. If Lead can't decide, Lead asks user.

7. **Spawn member agents** (not Lead — Lead is you, the main conversation):
   ```
   Agent({
     prompt: <filled role template>,
     team_name: "<team-name>",
     name: "<member-name>",
     subagent_type: "general-purpose"
   })
   ```

8. **Assign initial tasks** via TaskUpdate

9. **Begin operating as Lead** — follow the Lead operating instructions
   below

---

## Lead Operating Instructions

After spawning the team, you ARE the Lead. Follow these rules for the
rest of the session.

### Task Management

- Maintain the shared task list via TaskCreate/TaskUpdate/TaskList
- Assign **one task at a time** per member
- Members can propose new tasks — approve or reject before adding
- You can add tasks at any time based on results or user input

### Iteration Budget

Define max iterations per task based on risk:

| Risk | Max Tries | Examples |
|------|:---------:|---------|
| Low | 1 | Config tweak, flag toggle, scheduling hint |
| Medium | 3 | Structural code change, new optimization |
| High | 2 | Register pressure change, inline asm |

**Early skip**: Skip a task without implementing if investigation shows
it is fundamentally unviable. Document reasoning in status file.

### Decision Loop

```
Member reports results →
  Keep   → commit changes, update status, mark task done, assign next
  Fix    → send feedback to member, iterate (within budget)
  Revert → backup files first, revert, document findings, next task
```

### When All Tasks Are Done

Do NOT shut down. Ask the user:

a) "Add new tasks" → user provides tasks → continue
b) "Investigate and propose next steps" → create investigation task
c) "Shut down team" → only option that ends the team

### Status Updates

After each experiment/decision, update the status file:
- If recall enabled: the recall status.md
- If no recall: `.claude/teams/<team-name>/status.md`

Include: what was tried, results (measurements), keep/revert decision,
and why.

### Member Rotation (context > threshold)

When a member reports high context or you notice an idle notification
mentioning it:

1. Send `shutdown_request` to the member
2. Member saves status to `.claude/teams/<name>/status/<role>.md`:
   - Current task ID and subject
   - Progress: done / remaining
   - Key findings to carry forward
   - Last action taken
   - Files modified (uncommitted changes)
3. After member confirms shutdown, spawn a NEW agent with the same role
4. New agent reads the status file and picks up unfinished work

### Lead Rotation (your own context is high)

When your own context is getting high:

1. Update status.md with all results and current state
2. Shut down all members (they save status first)
3. Tell the user: "Team paused. Run `/hip-kernel-team load <name>` to
   resume."

---

## Operational Rules

These rules apply to ALL team members. Include them in every member
prompt.

### Output Handling

1. **All command stdout+stderr** → `/tmp/<team-name>/<role>/<desc>_NNN.txt`
   (using `2>&1`)
2. **Never pipe through tee, head, tail, grep, awk, sed, or any filter**
   when capturing — always save complete, unmodified output first
3. **Print the file path** for user visibility:
   `"Output saved to: /tmp/<team>/<role>/build_001.txt"`
4. **Read/analyze the saved file separately**: use Read tool with
   offset/limit, or spawn Explore subagent for large files
5. **Never print long output inline** in messages

### Context Efficiency

Three-tier hierarchy:
- **Lead** (main conversation): lightweight, long-lived, sees summaries
- **Members** (spawned agents): medium context, focused work, delegate
  heavy reads
- **Subagents** (spawned by members): short-lived, read large files,
  return compact summaries

File reading rules:
- < 100 lines: Read tool directly
- 100-500 lines: Read with offset/limit
- \> 500 lines: spawn Explore subagent
- Assembly files (.s): ALWAYS via subagent

### Git & File Safety

- **Never `git stash pop` or `git stash drop`** — always `git stash apply`
- **Backup before reverting**: `cp file file.bak` before `git checkout`
- **One task at a time** per member — no parallel experiments on same files
- **Clean build artifacts** before rebuilding (JIT cache, .so, build/)

### Message Efficiency

- Each message should advance work, not just acknowledge
- Implementer: review + implement + report in ONE message
- Report format: (1) what was done, (2) files changed, (3) results
- Don't send separate "I agree" then "I'm done" messages

---

## Recall Integration

### With Recall (preferred)

Paths resolved from config:
```
~/.local/share/claude/recall/<project>/branches/<branch>/tasks/<task>/
  status.md      — task progress, experiment log
  knowledge.md   — verified facts, measurements
  workflows.md   — build/test/bench commands
```

Responsibilities:
- **Lead**: updates status.md after each experiment/decision
- **Implementer**: reads workflows.md for commands, knowledge.md for
  constraints
- **Profiler**: writes measurements to knowledge.md
- **Researcher**: writes external findings to knowledge.md

### Without Recall (fallback)

```
.claude/teams/<team-name>/
  config.md        — team config
  status.md        — task progress, findings
  knowledge.md     — verified facts, measurements
  status/
    <role>.md      — per-member rotation status
```

Lead maintains status.md and knowledge.md directly.

### Member Bootstrap

Every member on spawn (or after rotation) bootstraps context:

```
Agent({
  description: "Bootstrap context from status file",
  subagent_type: "Explore",
  prompt: "Read <STATUS_FILE>. Extract: current state, recent results,
           active/remaining tasks, key findings. Under 50 lines."
})
```
