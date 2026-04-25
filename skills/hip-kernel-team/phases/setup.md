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

## Step 7: Team Name & Confirmation

Generate a short kebab-case team name from the goal (e.g.,
`ck-fmha-v3-opt`). Print a full summary of the config. Ask user to
confirm.

## Step 7b: Write Initial Context

Write your pre-conversation context (the system-reminder content you
received before the user's first message) to
`.claude/teams/<team-name>/initial-context.md`.

Use this format (~100 lines max):

~~~markdown
## CLAUDE.md Rules

<key rules from global and project CLAUDE.md — git policies, edit
conventions, output handling, commit style>

## Project Directives

<hook output: project directives, user profile, branch/task state —
whatever hooks emitted, passed through verbatim>

## Memory Index

<MEMORY.md index lines — file pointers only, not file contents>

## Available Skills

<name — description — file path, one per line, user-created skills only>
Note: You cannot invoke the Skill tool. To use a skill, Read its file
at the listed path.
~~~

**Include/exclude guidelines:**

| Section | Include | Exclude |
|---------|---------|---------|
| CLAUDE.md Rules | Git policies, edit conventions, output rules | Tool descriptions, system prompt boilerplate |
| Project Directives | Whatever hooks emitted (verbatim) | Nothing — pass through as-is |
| Memory Index | MEMORY.md lines (file pointers) | Memory file contents |
| Available Skills | User-created skills with resolved file paths | Built-in superpowers skills (not on disk) |

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

- Member rotation: 3 points (heavy=1, light=0.5), override on quality degradation
- Output directory: /tmp/<team-name>/
- Delegate reads above: 500 lines

## Evaluation Criteria

- <criteria defined by Lead based on goal>
```
