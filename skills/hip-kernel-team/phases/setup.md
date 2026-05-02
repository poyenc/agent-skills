# New Team Setup

Walk the user through these steps **one question at a time**. Use
`AskUserQuestion` when choices are discrete, plain text when open-ended.

## Step 1: Goal

Ask: "What is the goal for this team?"

The user describes the goal in natural language. This becomes the
`## Goal` section of the config.

## Step 2: Role Recommendation

Based on the goal, recommend a team composition from the role catalog.
Present your recommendation and reasoning, then ask the user to confirm
or override.

**Permanent role catalog** (user picks from these at setup):

| Role | Core Function |
|------|--------------|
| **Lead** | Task list management, team coordination, QA/Debugger spawn, keep/revert decisions, member rotation. Runs in the main conversation (not spawned). Always present. |
| **Implementer** | Code editing (HIP/C++/Python), build, structured output for QA, escalation-based workflow |
| **Profiler** | Assembly analysis, HW counter profiling (rocprofv3), benchmarking, regression diagnosis, ISA comparison |

**On-demand roles** (always available, Lead spawns per pipeline rules):

| Role | Spawn Type | Trigger |
|------|-----------|---------|
| **QA** | Subagent | After every implement stage (mandatory) |
| **Debugger** | Subagent | On implementer escalation |
| **Researcher** | Full team member | Knowledge gap or user request |

**Recommendation table:**

| Goal Pattern | Permanent Roles | Notes |
|---|---|---|
| Optimize existing kernel | Lead + Implementer + Profiler | Researcher on-demand if investigation needed |
| Debug correctness issue | Lead + Implementer + Profiler | Baseline + verify fix doesn't regress perf |
| Port algorithm from paper/reference | Lead + Implementer + Profiler | Researcher on-demand for paper analysis |
| Full development (new kernel) | Lead + Implementer + Profiler | Researcher on-demand |
| Investigate perf regression | Lead + Profiler | Researcher on-demand. Implementer on-demand for fixes |

**Soft warnings** (don't block, just inform):
- Implementer without Profiler: "Profiler is needed to verify perf
  meets production requirements."
- Only Lead: "Lead can absorb other roles but the team will be slower."
- Only Lead + Profiler: "An Implementer will be spawned on-demand if
  code changes are needed."

## Step 3: Constraints

Ask: "Any constraints? (compiler version, hardware target, compatibility
requirements, or 'none')"

## Step 4: Recall Detection

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

## Step 5: Key Files

Ask: "Any key reference files the team should know about? (source files,
reference implementations, or 'none — team will discover')"

## Step 6: Workflows

Ask: "Build/test/bench commands? (or 'team will figure out')"

If recall is present and a workflows.md exists for the detected task,
offer to auto-populate: "Found existing workflows in recall. Use those?"

## Step 6b: Model Selection

Ask: "Model preference for each member? (default: all inherit from
parent session, or specify per-role — e.g., 'profiler: sonnet')"

Also ask: "Model preferences for on-demand roles? (default: QA=sonnet,
Debugger=opus, Researcher=opus)"

If user says "default" or skips, use the defaults above.

## Step 7: Team Name & Confirmation

Generate a short kebab-case team name from the goal (e.g.,
`ck-fmha-v3-opt`). Print a full summary of the config. Ask user to
confirm.

## Step 8: Save & Spawn

1. Save config to `.claude/teams/<team-name>/config.md`
   (see [Config Format](#config-format) below)
2. After saving, read `${CLAUDE_SKILL_DIR}/phases/spawn.md` and follow
   it to spawn the team.

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

| Name | Role | Model | Notes |
|------|------|-------|-------|
| lead | Lead | (parent) | Coordinator (main conversation) |
| <name> | <Role> | <model> | <notes> |

## On-Demand Models

| Role | Model | Notes |
|------|-------|-------|
| QA | sonnet | Subagent, verification |
| Debugger | opus | Subagent, root cause analysis |
| Researcher | opus | Full team member, deep analysis |

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

- Member rotation: 3 points (heavy=1, light=0.5), override on quality degradation
- Output directory: /tmp/<team-name>/
- Delegate reads above: 500 lines

## Evaluation Criteria

- <criteria defined by Lead based on goal>
```
