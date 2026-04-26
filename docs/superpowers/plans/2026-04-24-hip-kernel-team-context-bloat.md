# hip-kernel-team Context-Bloat Reduction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce each spawned team member's initial context consumption from ~15% to ~5% by eliminating bootstrap subagents, deduplicating lead instructions, and simplifying communication rules.

**Architecture:** Three independent fixes applied sequentially to the `skills/hip-kernel-team/` directory. All changes are to markdown skill files — no code, no tests. Validation is done via grep/file-existence checks after each fix.

**Tech Stack:** Markdown (skill definition files), git

**Spec:** `docs/superpowers/specs/2026-04-24-hip-kernel-team-context-bloat-design.md`

---

### Task 1: Remove bootstrap subagent from implementer.md

**Files:**
- Modify: `skills/hip-kernel-team/roles/implementer.md:88-126`

- [ ] **Step 1: Delete the Bootstrap section**

In `skills/hip-kernel-team/roles/implementer.md`, delete lines 88-102 (the entire `## Bootstrap` section):

```markdown
## Bootstrap

On spawn, immediately read status files to understand current state:

\```
Agent({
  description: "Bootstrap context",
  subagent_type: "Explore",
  prompt: "Read {{STATUS_FILE}}. Also check if
           .claude/teams/{{TEAM_NAME}}/status/implementer.md exists
           and read it — this contains handoff notes from the previous
           rotation (unfinished tasks, key findings, uncommitted files).
           Extract: current state, recent results, active/remaining
           tasks, key findings, any rotation handoff. Under 50 lines."
})
\```
```

- [ ] **Step 2: Add Current State section**

In `skills/hip-kernel-team/roles/implementer.md`, after `{{WORKFLOWS}}` (line 46), add:

```markdown

## Current State

{{CURRENT_STATE}}
```

- [ ] **Step 3: Update First Actions**

In `skills/hip-kernel-team/roles/implementer.md`, replace the `## First Actions` section (previously lines 124-126, now shifted after deletions/additions):

Replace:
```markdown
## First Actions

1. Bootstrap context via subagent (see above)
2. Check TaskList for assigned tasks
3. Wait for the Lead to assign work or propose a plan
```

With:
```markdown
## First Actions

1. Check TaskList for assigned tasks
2. Wait for the Lead to assign work or propose a plan
```

- [ ] **Step 4: Verify no bootstrap references remain**

Run: `grep -n -i "bootstrap" skills/hip-kernel-team/roles/implementer.md`
Expected: no output (no matches)

Run: `grep -n "CURRENT_STATE" skills/hip-kernel-team/roles/implementer.md`
Expected: one match showing `{{CURRENT_STATE}}`

---

### Task 2: Remove bootstrap subagent from profiler.md

**Files:**
- Modify: `skills/hip-kernel-team/roles/profiler.md:111-150`

- [ ] **Step 1: Delete the Bootstrap section**

In `skills/hip-kernel-team/roles/profiler.md`, delete lines 111-127 (the entire `## Bootstrap` section):

```markdown
## Bootstrap

On spawn, immediately read status files to understand current state:

\```
Agent({
  description: "Bootstrap context",
  subagent_type: "Explore",
  prompt: "Read {{STATUS_FILE}}. Also check if
           .claude/teams/{{TEAM_NAME}}/status/profiler.md exists
           and read it — this contains handoff notes from the previous
           rotation (unfinished tasks, baseline numbers, last analysis).
           Extract: current state, recent results, active/remaining
           tasks, key findings, baseline numbers, any rotation handoff.
           Under 50 lines."
})
\```
```

- [ ] **Step 2: Add Current State section**

In `skills/hip-kernel-team/roles/profiler.md`, after `{{WORKFLOWS}}` (line 41), add:

```markdown

## Current State

{{CURRENT_STATE}}
```

- [ ] **Step 3: Update First Actions**

In `skills/hip-kernel-team/roles/profiler.md`, replace the `## First Actions` section:

Replace:
```markdown
## First Actions

1. Bootstrap context via subagent (see above)
2. Check TaskList for assigned tasks
3. If baseline capture is needed, start immediately
4. Otherwise wait for Lead to assign work
```

With:
```markdown
## First Actions

1. Check TaskList for assigned tasks
2. If baseline capture is needed, start immediately
3. Otherwise wait for Lead to assign work
```

- [ ] **Step 4: Verify no bootstrap references remain**

Run: `grep -n -i "bootstrap" skills/hip-kernel-team/roles/profiler.md`
Expected: no output

Run: `grep -n "CURRENT_STATE" skills/hip-kernel-team/roles/profiler.md`
Expected: one match showing `{{CURRENT_STATE}}`

---

### Task 3: Remove bootstrap subagent from researcher.md

**Files:**
- Modify: `skills/hip-kernel-team/roles/researcher.md:128-167`

- [ ] **Step 1: Delete the Bootstrap section**

In `skills/hip-kernel-team/roles/researcher.md`, delete lines 128-144 (the entire `## Bootstrap` section):

```markdown
## Bootstrap

On spawn, immediately read status and knowledge files:

\```
Agent({
  description: "Bootstrap context",
  subagent_type: "Explore",
  prompt: "Read {{STATUS_FILE}} and {{KNOWLEDGE_FILE}}. Also check if
           .claude/teams/{{TEAM_NAME}}/status/researcher.md exists
           and read it — this contains handoff notes from the previous
           rotation (unfinished investigations, key findings, what was
           being researched). Extract: current state, recent findings,
           what has already been investigated, key reference patterns,
           any rotation handoff. Under 60 lines."
})
\```
```

- [ ] **Step 2: Add Current State section**

In `skills/hip-kernel-team/roles/researcher.md`, after `{{WORKFLOWS}}` (line 41), add:

```markdown

## Current State

{{CURRENT_STATE}}
```

- [ ] **Step 3: Update First Actions**

In `skills/hip-kernel-team/roles/researcher.md`, replace the `## First Actions` section:

Replace:
```markdown
## First Actions

1. Bootstrap context via subagent (see above)
2. Check TaskList for assigned tasks
3. If assigned a research task, begin investigation
4. Otherwise wait for Lead to assign work
```

With:
```markdown
## First Actions

1. Check TaskList for assigned tasks
2. If assigned a research task, begin investigation
3. Otherwise wait for Lead to assign work
```

- [ ] **Step 4: Verify no bootstrap references remain**

Run: `grep -n -i "bootstrap" skills/hip-kernel-team/roles/researcher.md`
Expected: no output

Run: `grep -n "CURRENT_STATE" skills/hip-kernel-team/roles/researcher.md`
Expected: one match showing `{{CURRENT_STATE}}`

---

### Task 4: Remove bootstrap from operate.md and add state summary step to spawn.md

**Files:**
- Modify: `skills/hip-kernel-team/phases/operate.md:170-185`
- Modify: `skills/hip-kernel-team/phases/spawn.md:30-43,84-86`

- [ ] **Step 1: Delete Member Bootstrap section from operate.md**

In `skills/hip-kernel-team/phases/operate.md`, delete lines 168-185 (the `### Member Bootstrap` section through end of file):

```markdown

### Member Bootstrap

Every member on spawn (or after rotation) bootstraps context:

\```
Agent({
  description: "Bootstrap context from status file",
  subagent_type: "Explore",
  prompt: "Read <STATUS_FILE>. Also check if
           .claude/teams/<team-name>/status/<role>.md exists and read
           it — this contains handoff notes from the previous rotation
           (unfinished tasks, key findings, uncommitted files).
           Extract: current state, recent results, active/remaining
           tasks, key findings, any rotation handoff. Under 50 lines."
})
\```
```

- [ ] **Step 2: Add state summary step to spawn.md**

In `skills/hip-kernel-team/phases/spawn.md`, after the `## 4. Read role templates` section (after line 25), add:

```markdown

## 5. Prepare inline state summary

For each member being spawned, read `{{STATUS_FILE}}` and check if
`.claude/teams/<team-name>/status/<role>.md` exists. Compose a compact
summary (under 10 lines) of: current state, recent results, active
tasks, key findings, and any rotation handoff notes. If no status files
exist, use: `"Fresh team -- no prior state. Wait for task assignment."`
```

- [ ] **Step 3: Renumber spawn.md steps 5-9 to 6-10**

Renumber the existing steps that follow:
- `## 5. Fill placeholders` → `## 6. Fill placeholders`
- `## 6. Generate communication rules` → `## 7. Generate communication rules`
- `## 7. Spawn member agents` → `## 8. Spawn member agents`
- `## 8. Assign initial tasks` → `## 9. Assign initial tasks`
- `## 9. Begin operating as Lead` → `## 10. Begin operating as Lead`

- [ ] **Step 4: Add CURRENT_STATE to placeholder table in spawn.md**

In `skills/hip-kernel-team/phases/spawn.md`, in the placeholder table (now under step 6), add a new row after `{{WORKFLOWS}}`:

```markdown
| `{{CURRENT_STATE}}` | Inline state summary prepared in step 5 |
```

- [ ] **Step 5: Verify changes**

Run: `grep -n -i "bootstrap" skills/hip-kernel-team/phases/operate.md`
Expected: no output

Run: `grep -n "CURRENT_STATE" skills/hip-kernel-team/phases/spawn.md`
Expected: one match in the placeholder table

Run: `grep -n "Prepare inline state summary" skills/hip-kernel-team/phases/spawn.md`
Expected: one match

---

### Task 5: Commit Fix 1

- [ ] **Step 1: Commit all bootstrap removal changes**

```bash
git add skills/hip-kernel-team/roles/implementer.md \
      skills/hip-kernel-team/roles/profiler.md \
      skills/hip-kernel-team/roles/researcher.md \
      skills/hip-kernel-team/phases/operate.md \
      skills/hip-kernel-team/phases/spawn.md
git commit -m "refactor: replace bootstrap subagent with inline state summary

Members no longer spawn an Explore subagent on boot to read status
files. Instead, the lead reads status files and injects a compact
summary via the {{CURRENT_STATE}} placeholder in each member's spawn
prompt. Saves ~10% context per member on fresh spawns."
```

---

### Task 6: Merge operate.md into lead.md — Status Updates section

**Files:**
- Modify: `skills/hip-kernel-team/roles/lead.md:65`

- [ ] **Step 1: Add Status Updates section to lead.md**

In `skills/hip-kernel-team/roles/lead.md`, after the Decision Loop section (after line 65, the closing triple-backtick of the decision loop code block), add:

```markdown

## Status Updates

After each experiment/decision, update the status file:
- If recall enabled: the recall status.md
- If no recall: `.claude/teams/{{TEAM_NAME}}/status.md`

Include: what was tried, results (measurements), keep/revert decision,
and why.
```

- [ ] **Step 2: Verify section exists**

Run: `grep -n "Status Updates" skills/hip-kernel-team/roles/lead.md`
Expected: one match

---

### Task 7: Merge operate.md into lead.md — Operational Rules section

**Files:**
- Modify: `skills/hip-kernel-team/roles/lead.md` (append before Evaluation Criteria)

- [ ] **Step 1: Add Rules You Enforce on Members section**

In `skills/hip-kernel-team/roles/lead.md`, before the `## Evaluation Criteria` section (which is currently the last section), add:

```markdown

---

## Rules You Enforce on Members

These rules apply to ALL team members. Enforce them.

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
- > 500 lines: spawn Explore subagent
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
```

- [ ] **Step 2: Verify section exists**

Run: `grep -n "Rules You Enforce" skills/hip-kernel-team/roles/lead.md`
Expected: one match

---

### Task 8: Merge operate.md into lead.md — Recall Integration section

**Files:**
- Modify: `skills/hip-kernel-team/roles/lead.md` (append after Rules section, before Evaluation Criteria)

- [ ] **Step 1: Add Recall Integration section**

In `skills/hip-kernel-team/roles/lead.md`, after the "Rules You Enforce on Members" section and before `## Evaluation Criteria`, add:

```markdown

## Recall Integration

### With Recall (preferred)

Paths resolved from config:
\```
~/.local/share/claude/recall/<project>/branches/<branch>/tasks/<task>/
  status.md      — task progress, experiment log
  knowledge.md   — verified facts, measurements
  workflows.md   — build/test/bench commands
\```

Responsibilities:
- **Lead**: updates status.md after each experiment/decision
- **Implementer**: reads workflows.md for commands, knowledge.md for
  constraints
- **Profiler**: writes measurements to knowledge.md
- **Researcher**: writes external findings to knowledge.md

### Without Recall (fallback)

\```
.claude/teams/<team-name>/
  config.md        — team config
  status.md        — task progress, findings
  knowledge.md     — verified facts, measurements
  status/
    <role>.md      — per-member rotation status
\```

Lead maintains status.md and knowledge.md directly.
```

- [ ] **Step 2: Verify section exists**

Run: `grep -n "Recall Integration" skills/hip-kernel-team/roles/lead.md`
Expected: one match

---

### Task 9: Delete operate.md and update spawn.md reference

**Files:**
- Delete: `skills/hip-kernel-team/phases/operate.md`
- Modify: `skills/hip-kernel-team/phases/spawn.md` (step 10, formerly step 9)

- [ ] **Step 1: Update spawn.md reference**

In `skills/hip-kernel-team/phases/spawn.md`, replace the last step (currently `## 10. Begin operating as Lead`):

Replace:
```markdown
## 10. Begin operating as Lead

Read `${CLAUDE_SKILL_DIR}/phases/operate.md` and follow the Lead
operating instructions for the rest of the session.
```

With:
```markdown
## 10. Begin operating as Lead

Follow the Lead instructions in `${CLAUDE_SKILL_DIR}/roles/lead.md`
for the rest of the session.
```

- [ ] **Step 2: Delete operate.md**

```bash
git rm skills/hip-kernel-team/phases/operate.md
```

- [ ] **Step 3: Verify**

Run: `test -f skills/hip-kernel-team/phases/operate.md && echo "EXISTS" || echo "DELETED"`
Expected: `DELETED`

Run: `grep -rn "operate.md" skills/hip-kernel-team/`
Expected: no output (no remaining references)

---

### Task 10: Commit Fix 2

- [ ] **Step 1: Commit the merge**

```bash
git add skills/hip-kernel-team/roles/lead.md \
      skills/hip-kernel-team/phases/spawn.md
git commit -m "refactor: merge operate.md into lead.md

Consolidate all lead behavior into roles/lead.md — the single source
of truth. Unique content from operate.md (Status Updates, Operational
Rules, Recall Integration) is absorbed; duplicated sections are dropped.
phases/operate.md is deleted."
```

---

### Task 11: Simplify communication rules in member templates

**Files:**
- Modify: `skills/hip-kernel-team/roles/implementer.md:35-36`
- Modify: `skills/hip-kernel-team/roles/profiler.md:30-31`
- Modify: `skills/hip-kernel-team/roles/researcher.md:30-31`

- [ ] **Step 1: Replace comm rules in implementer.md**

In `skills/hip-kernel-team/roles/implementer.md`, replace:

```markdown
## Communication

{{COMMUNICATION_RULES}}
```

With:

```markdown
## Communication

Report to lead. DM peers when directly relevant. Escalate disagreements
to lead.
```

- [ ] **Step 2: Replace comm rules in profiler.md**

In `skills/hip-kernel-team/roles/profiler.md`, replace:

```markdown
## Communication

{{COMMUNICATION_RULES}}
```

With:

```markdown
## Communication

Report to lead. DM peers when directly relevant. Escalate disagreements
to lead.
```

- [ ] **Step 3: Replace comm rules in researcher.md**

In `skills/hip-kernel-team/roles/researcher.md`, replace:

```markdown
## Communication

{{COMMUNICATION_RULES}}
```

With:

```markdown
## Communication

Report to lead. DM peers when directly relevant. Escalate disagreements
to lead.
```

- [ ] **Step 4: Verify no COMMUNICATION_RULES placeholders remain in member templates**

Run: `grep -rn "COMMUNICATION_RULES" skills/hip-kernel-team/roles/`
Expected: no output (lead.md should also have been updated — see Task 12)

Note: lead.md still has the placeholder at this point. That's fine — Task 12 handles it.

---

### Task 12: Simplify communication rules in lead.md and spawn.md

**Files:**
- Modify: `skills/hip-kernel-team/roles/lead.md:37-39`
- Modify: `skills/hip-kernel-team/phases/spawn.md` (placeholder table + step 7)

- [ ] **Step 1: Replace comm rules in lead.md**

In `skills/hip-kernel-team/roles/lead.md`, replace:

```markdown
## Communication

{{COMMUNICATION_RULES}}
```

With:

```markdown
## Communication

Report to members via task assignments and direct messages. Escalate
unresolvable disagreements to the user.
```

(Lead's comm rule is slightly different — the lead doesn't "report to lead".)

- [ ] **Step 2: Remove comm rules generation step from spawn.md**

In `skills/hip-kernel-team/phases/spawn.md`, delete the entire communication rules generation step (currently step 7 after renumbering in Task 4). This is the section that starts with `## 7. Generate communication rules` and includes the role-pair table and escalation note.

Delete:
```markdown
## 7. Generate communication rules

Generate from the roles present. Only include pairs where both roles
exist on the team:

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
```

- [ ] **Step 3: Remove COMMUNICATION_RULES from placeholder table in spawn.md**

In the placeholder table (step 6), delete the row:

```markdown
| `{{COMMUNICATION_RULES}}` | Generated from role pairs present (see below) |
```

- [ ] **Step 4: Renumber remaining spawn.md steps**

After removing the comm rules generation step:
- `## 8. Spawn member agents` → `## 7. Spawn member agents`
- `## 9. Assign initial tasks` → `## 8. Assign initial tasks`
- `## 10. Begin operating as Lead` → `## 9. Begin operating as Lead`

- [ ] **Step 5: Verify**

Run: `grep -rn "COMMUNICATION_RULES" skills/hip-kernel-team/`
Expected: no output

Run: `grep -rn "Generate communication rules" skills/hip-kernel-team/`
Expected: no output

---

### Task 13: Commit Fix 3

- [ ] **Step 1: Commit the comm rules simplification**

```bash
git add skills/hip-kernel-team/roles/implementer.md \
      skills/hip-kernel-team/roles/profiler.md \
      skills/hip-kernel-team/roles/researcher.md \
      skills/hip-kernel-team/roles/lead.md \
      skills/hip-kernel-team/phases/spawn.md
git commit -m "refactor: replace generated communication rules with one-liner

The role-pair communication table was generated per spawn and injected
into every member prompt but never enforced. Replace with a hardcoded
one-liner. Remove the generation step from spawn.md. Saves ~12 lines
per member prompt."
```

---

### Task 14: Final validation

- [ ] **Step 1: Verify no bootstrap or comm rules artifacts remain**

```bash
grep -rn "bootstrap" skills/hip-kernel-team/ | grep -iv "TODO"
grep -rn "COMMUNICATION_RULES" skills/hip-kernel-team/
grep -rn "operate.md" skills/hip-kernel-team/
```

Expected: all three commands produce no output.

- [ ] **Step 2: Verify CURRENT_STATE placeholder is in all member templates**

```bash
grep -l "CURRENT_STATE" skills/hip-kernel-team/roles/
```

Expected: `implementer.md`, `profiler.md`, `researcher.md` (3 files, NOT lead.md)

- [ ] **Step 3: Verify spawn.md step numbering is sequential**

```bash
grep "^## [0-9]" skills/hip-kernel-team/phases/spawn.md
```

Expected: steps numbered 1 through 9, no gaps, no duplicates.

- [ ] **Step 4: Update TODO.md**

In `skills/hip-kernel-team/TODO.md`, move issues 1, 2, and 7 to the `## Completed` section with a note: `**Status: done — context-bloat reduction.**`
