# Hip Kernel Team: Ownership & Dedup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restrict knowledge/status file writes to Lead only and eliminate rule duplication across member templates by extracting shared rules into a single file.

**Architecture:** Create `roles/shared.md` as the single source of shared member rules. Inject it into each member's prompt at spawn time via a new step in `spawn.md`. Remove duplicated sections from member templates. Rewrite Lead's Recall Integration and enforcement sections to reflect sole ownership of knowledge/status files.

**Tech Stack:** Markdown template files, no code.

**Spec:** `docs/superpowers/specs/2026-04-25-hip-kernel-team-ownership-and-dedup-design.md`

**Skill base dir:** `/home/poyechen/.claude/skills/hip-kernel-team`

---

### Task 1: Create roles/shared.md

**Files:**
- Create: `roles/shared.md`

- [ ] **Step 1: Create the shared rules file**

Write `roles/shared.md` with the following content. This is the
canonical copy of all rules that apply to every teammate.

```markdown
## Output Handling

All command output goes to `{{OUTPUT_DIR}}`:

\`\`\`bash
<command> > {{OUTPUT_DIR}}<desc>_NNN.txt 2>&1
\`\`\`

- Never pipe through tee, head, tail, grep, awk, sed, or any filter
  when capturing output
- Print the file path so the user can trace progress
- Read/analyze the saved file separately via Read or Explore subagent
- Never print long output inline in messages

## Context Efficiency

- Files < 100 lines: read directly
- Files 100-500 lines: use offset/limit
- Files > 500 lines: spawn Explore subagent
- Assembly files (.s): ALWAYS via Explore subagent
- Delegate any independent, context-heavy work to short-lived subagents

## Git & File Safety

- Never `git stash pop` or `git stash drop` — always `git stash apply`
- Backup before reverting: `cp file file.bak` before `git checkout`
- Clean build artifacts before rebuilding (JIT cache, .so, build/)

## Communication

Report to lead. DM peers when directly relevant. Escalate disagreements
to lead.

## On Shutdown

The Lead will first ask you to save status before sending
shutdown_request. When asked to prepare for rotation:

1. Ensure all work is saved (edits, analysis results)
2. Save status to `.claude/teams/{{TEAM_NAME}}/status/<role>.md`:
   - Current task ID and subject
   - Progress: done / remaining
   - Key findings
3. Confirm to Lead that status is saved

When you then receive the shutdown_request, approve it.

## First Actions

1. Check TaskList for assigned tasks
2. Wait for the Lead to assign work
```

- [ ] **Step 2: Commit**

```bash
git add roles/shared.md
git commit -m "feat(hip-kernel-team): create shared rules file for member templates"
```

---

### Task 2: Strip shared sections from implementer.md

**Files:**
- Modify: `roles/implementer.md`

- [ ] **Step 1: Read the current file**

Read `roles/implementer.md` to confirm current content.

- [ ] **Step 2: Remove shared sections**

Remove these sections (they now live in `shared.md`):

1. **Lines 34-37** — the `## Communication` section and its content
   (`Report to lead. DM peers when directly relevant...`)

   Keep all template variable sections (`## Goal`, `## Constraints`,
   `## Team Roster`, `## Key Files`, `## Environment & Workflows`,
   `## Current State`, `## Session Context`) — these are per-spawn
   config, not shared rules.

2. **Lines 56-69** — the `## Output Handling` section (entire block
   from header through the 4 bullet points)

3. **Lines 71-76** — the `## Context Efficiency` section (entire block
   from header through assembly rule, EXCEPT the Compile-Safety
   Checklist which is implementer-specific and starts at line 78)

4. **Lines 89-94** — the `## Git & File Safety` section (3 bullets)

5. **Lines 96-111** — the `## On Shutdown` section (entire block)

6. **Lines 113-117** — the `## First Actions` section (entire block)

After removal, `implementer.md` should contain only:
- Role description (lines 1-19): role intro, the 6 responsibilities,
  and the "Do NOT send separate messages" rule
- Goal/Constraints/Team Roster/Key Files/Environment/Workflows/
  CurrentState/SessionContext template sections (lines 20-55)
- Compile-Safety Checklist (lines 78-88)

- [ ] **Step 3: Verify the file reads cleanly**

Read the modified file and confirm no dangling references or orphaned
headers remain.

- [ ] **Step 4: Commit**

```bash
git add roles/implementer.md
git commit -m "refactor(hip-kernel-team): remove shared sections from implementer template"
```

---

### Task 3: Strip shared sections from profiler.md

**Files:**
- Modify: `roles/profiler.md`

- [ ] **Step 1: Read the current file**

Read `roles/profiler.md` to confirm current content.

- [ ] **Step 2: Remove shared sections**

Remove these sections:

1. **Lines 29-32** — `## Communication` section
2. **Lines 55-66** — `## Output Handling` section
3. **Lines 68-73** — `## Context Efficiency` section (the 4 file-size
   rules). KEEP the `### Assembly Analysis Pattern` (lines 75-93) and
   `### Benchmark Analysis` (lines 95-103) and
   `### Register Pressure Analysis` (lines 105-113) — these are
   profiler-specific.
4. **Lines 115-118** — `## Git & File Safety` section
5. **Lines 120-133** — `## On Shutdown` section
6. **Lines 135-140** — `## First Actions` section

After removal, `profiler.md` should contain only:
- Role description (lines 1-17): role intro, the 8 responsibilities
- Template variable sections (Goal through Session Context)
- Assembly Analysis Pattern
- Benchmark Analysis
- Register Pressure Analysis

- [ ] **Step 3: Verify the file reads cleanly**

- [ ] **Step 4: Commit**

```bash
git add roles/profiler.md
git commit -m "refactor(hip-kernel-team): remove shared sections from profiler template"
```

---

### Task 4: Strip shared sections and knowledge write from researcher.md

**Files:**
- Modify: `roles/researcher.md`

- [ ] **Step 1: Read the current file**

Read `roles/researcher.md` to confirm current content.

- [ ] **Step 2: Remove shared sections**

Remove these sections:

1. **Lines 32-35** — `## Communication` section
2. **Lines 56-69** — `## Output Handling` section
3. **Lines 71-75** — `## Context Efficiency` section (the 4 file-size
   rules). KEEP the `### External Code Analysis Pattern` (lines 77-92)
   and `### Compiler Investigation Pattern` (lines 94-104) and
   `### Findings Report Format` (lines 106-126) — these are
   researcher-specific.
4. **Lines 128-130** — Remove the knowledge file write instruction:
   ```
   Write verified findings to the knowledge file:
   - If recall enabled: `{{KNOWLEDGE_FILE}}`
   - If no recall: `.claude/teams/{{TEAM_NAME}}/knowledge.md`
   ```
   The Researcher no longer writes to knowledge files directly. The
   Lead promotes findings after keep/revert decisions.
5. **Lines 132-133** — `## Git & File Safety` section
6. **Lines 139-150** — `## On Shutdown` section
7. **Lines 152-157** — `## First Actions` section

After removal, `researcher.md` should contain only:
- Role description (lines 1-17): role intro, the 7 responsibilities
- Template variable sections (Goal through Session Context)
- External Code Analysis Pattern
- Compiler Investigation Pattern
- Findings Report Format (WITHOUT the knowledge file write at the end)

- [ ] **Step 3: Verify the file reads cleanly**

- [ ] **Step 4: Commit**

```bash
git add roles/researcher.md
git commit -m "refactor(hip-kernel-team): remove shared sections and knowledge write from researcher"
```

---

### Task 5: Update lead.md — Recall Integration and Rules enforcement

**Files:**
- Modify: `roles/lead.md`

- [ ] **Step 1: Rewrite the Recall Integration section**

Replace lines 186-216 (from `## Recall Integration` to the end of the
"Without Recall" block) with:

```markdown
## Recall Integration

### With Recall (preferred)

Paths resolved from config:
\`\`\`
~/.local/share/claude/recall/<project>/branches/<branch>/tasks/<task>/
  status.md      — task progress, experiment log
  knowledge.md   — verified facts, measurements
  workflows.md   — build/test/bench commands
\`\`\`

Only you (the Lead) write to status.md and knowledge.md. Members
produce results in their output files. After a keep/revert decision,
promote verified findings to knowledge.md.

Members read workflows.md for build/test/bench commands (injected in
their prompt via {{WORKFLOWS}}).

### Without Recall (fallback)

\`\`\`
.claude/teams/<team-name>/
  config.md        — team config
  status.md        — task progress, findings
  knowledge.md     — verified facts, measurements
  status/
    <role>.md      — per-member rotation status
\`\`\`

You maintain status.md and knowledge.md directly.
```

- [ ] **Step 2: Replace "Rules You Enforce on Members" section**

Replace lines 139-184 (from the `---` separator through
`### Message Efficiency`) with:

```markdown
---

## Rules You Enforce on Members

Members receive shared rules in their prompt (from `roles/shared.md`).
Watch for violations of:
- Output handling: inline dumps instead of file paths
- Context efficiency: reading large files directly instead of using
  subagents
- Git safety: stash pop/drop, reverting without backup
- Message efficiency: separate "I agree" then "I'm done" messages
  instead of review + implement + report in one turn
```

- [ ] **Step 3: Fix "Two-step shutdown" label**

Change line 111 from:
```
Two-step shutdown:
```
To:
```
Rotation shutdown procedure:
```

- [ ] **Step 4: Verify the file reads cleanly**

Read the full modified file end-to-end. Confirm:
- No stale references to members writing to knowledge.md
- The Recall Integration section shows Lead as sole writer
- The enforcement section is a concise summary, not restated rules
- "Two-step" label is fixed

- [ ] **Step 5: Commit**

```bash
git add roles/lead.md
git commit -m "refactor(hip-kernel-team): Lead owns knowledge/status writes, condense enforcement rules"
```

---

### Task 6: Update spawn.md — add shared.md injection, remove KNOWLEDGE_FILE

**Files:**
- Modify: `phases/spawn.md`

- [ ] **Step 1: Add shared.md injection step**

After step 4 ("Read role templates") and before step 5 ("Prepare
inline state summary"), insert a new step. Renumber subsequent steps.

Insert after line 24:

```markdown
## 5. Read shared rules

Read `${CLAUDE_SKILL_DIR}/roles/shared.md` — this content is appended
to every member's prompt after their role template.
```

Renumber old steps 5→6, 6→7, 7→8, 8→9, 9→10.

- [ ] **Step 2: Update the spawn instruction**

In the renamed step 8 (old step 7, "Spawn member agents"), update the
prompt description to show the combined template:

Change:
```
  prompt: <filled role template>,
```
To:
```
  prompt: <filled role template + shared rules>,
```

- [ ] **Step 3: Remove KNOWLEDGE_FILE from placeholder table**

In the renamed step 7 (old step 6, "Fill placeholders"), remove the
row:
```
| `{{KNOWLEDGE_FILE}}` | Recall path or `.claude/teams/<name>/knowledge.md` |
```

- [ ] **Step 4: Verify the file reads cleanly**

Read the full modified file. Confirm:
- Steps are numbered 1-10 sequentially
- shared.md injection happens before placeholder filling
- `{{KNOWLEDGE_FILE}}` is gone from the placeholder table
- Spawn instruction shows combined template

- [ ] **Step 5: Commit**

```bash
git add phases/spawn.md
git commit -m "feat(hip-kernel-team): inject shared.md at spawn, remove KNOWLEDGE_FILE placeholder"
```

---

### Task 7: Verification

**Files:** All modified files (read-only verification)

- [ ] **Step 1: Grep for KNOWLEDGE_FILE**

```bash
grep -r "KNOWLEDGE_FILE" /home/poyechen/.claude/skills/hip-kernel-team/
```

Expected: no results (it should be fully removed).

- [ ] **Step 2: Grep for duplicated rule text**

```bash
grep -r "Never pipe through" /home/poyechen/.claude/skills/hip-kernel-team/roles/
grep -r "git stash pop" /home/poyechen/.claude/skills/hip-kernel-team/roles/
grep -r "stash apply" /home/poyechen/.claude/skills/hip-kernel-team/roles/
```

Expected: each pattern appears only in `shared.md` (and `lead.md`'s
concise enforcement summary for stash, without the full rule text).

- [ ] **Step 3: Read each modified file end-to-end**

Read and verify internal consistency of:
1. `roles/shared.md` — complete, no placeholders missing
2. `roles/lead.md` — no stale member-writes-to-knowledge references
3. `roles/implementer.md` — only role-specific content remains
4. `roles/profiler.md` — only role-specific content remains
5. `roles/researcher.md` — no knowledge file write, only role-specific
6. `phases/spawn.md` — steps numbered correctly, shared.md injected

- [ ] **Step 4: Verify no orphaned template variables**

```bash
grep -r "{{KNOWLEDGE_FILE}}" /home/poyechen/.claude/skills/hip-kernel-team/
```

Expected: no results.

```bash
grep -r "{{OUTPUT_DIR}}" /home/poyechen/.claude/skills/hip-kernel-team/roles/
```

Expected: appears in `shared.md` only (not in individual member
templates).
