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
hooks:
  PreToolUse:
    - matcher: "Agent"
      hooks:
        - type: command
          # Workaround: ${CLAUDE_SKILL_DIR} not expanded in frontmatter (claude-code#36135)
          command: "~/.claude/skills/hip-kernel-team/scripts/inject-team-context.sh"
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

Parse `$ARGUMENTS` and follow the matching path:

### Empty or unrecognized → New Team

Read `${CLAUDE_SKILL_DIR}/phases/setup.md` and follow it to create a
new team through conversational setup.

### `load <name>` → Resume Team

Read `${CLAUDE_SKILL_DIR}/phases/resume.md` and follow it to re-launch
team **<name>** from its saved config.

### `list` → List Saved Teams

1. Glob `.claude/teams/*/config.md`
2. For each config, extract: name, goal (first 80 chars), roles, created
   date from frontmatter
3. Print a table of all saved teams

### `update <name>` → Modify Config

1. Read `.claude/teams/<name>/config.md`
2. Print the current config
3. Ask: "What would you like to change?"
4. Update the config file based on user input
