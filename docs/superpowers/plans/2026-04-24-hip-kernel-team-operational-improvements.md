# hip-kernel-team Operational Improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add task dependency guidance, unresponsive member protocol, and rotation point tracking clarification to the lead's operating instructions.

**Architecture:** Three inline additions to `roles/lead.md`. No new files or sections. Single commit.

**Tech Stack:** Markdown (skill definition files), git

**Spec:** `docs/superpowers/specs/2026-04-24-hip-kernel-team-operational-improvements-design.md`

---

### Task 1: Add all three operational improvements to lead.md

**Files:**
- Modify: `skills/hip-kernel-team/roles/lead.md:17-18` (dependency bullet)
- Modify: `skills/hip-kernel-team/roles/lead.md:92-94` (rotation tracking)
- Modify: `skills/hip-kernel-team/roles/lead.md:106-107` (unresponsive member subsection)

- [ ] **Step 1: Add task dependency bullet to Your Role**

In `skills/hip-kernel-team/roles/lead.md`, in the `## Your Role` bullet list, after the task-role matching bullet (lines 15-17) and before "Approve or reject member-proposed tasks" (line 18), add:

```markdown
- Use `addBlockedBy` when creating tasks with dependencies. Do not
  assign a task that has unresolved blockers — check `blockedBy` in
  TaskList output before assigning.
```

- [ ] **Step 2: Add rotation tracking clarification**

In `skills/hip-kernel-team/roles/lead.md`, in the `## Member Rotation` section, after the sentence "Rotate at the configured threshold (default: 3 points)." (line 93) and before "Override on", add:

Replace:
```markdown
Rotate at the configured threshold (default: 3 points). Override on
quality degradation regardless of points. Never rotate mid-task.
```

With:
```markdown
Rotate at the configured threshold (default: 3 points). Keep a mental
tally per member — reset to 0 after rotation. Override on quality
degradation regardless of points. Never rotate mid-task.
```

- [ ] **Step 3: Add unresponsive member subsection**

In `skills/hip-kernel-team/roles/lead.md`, after the "Two-step shutdown" numbered list (after the line "5. Assign unfinished task") and before `## Your Own Rotation`, add:

```markdown

### Unresponsive Members

Track idle notifications where the member's last message lacked
progress or results. Ignore idle after messages that indicate active
work (e.g., waiting for a command to finish, analysis in progress).

1. **1st unproductive idle**: send a check-in message asking for status
2. **2nd unproductive idle**: read their output files in
   `/tmp/<team-name>/<role>/` directly to assess progress
3. **3rd unproductive idle**: reassign the task to the same role (rotate
   the member if needed) or escalate to user
```

- [ ] **Step 4: Verify**

Run:
```bash
grep -n "addBlockedBy" skills/hip-kernel-team/roles/lead.md
grep -n "mental tally" skills/hip-kernel-team/roles/lead.md
grep -n "Unresponsive Members" skills/hip-kernel-team/roles/lead.md
```

Expected: one match each.

- [ ] **Step 5: Commit**

```bash
git add skills/hip-kernel-team/roles/lead.md
git commit -m "feat: add task dependencies, idle protocol, and rotation tracking to lead

Add addBlockedBy guidance for task dependency management, three-step
protocol for unresponsive members, and clarify that rotation points
are tracked in-memory and reset after each rotation."
```

---

### Task 2: Update TODO.md

**Files:**
- Modify: `skills/hip-kernel-team/TODO.md`

- [ ] **Step 1: Move issues 3, 4, 6 to Completed**

In `skills/hip-kernel-team/TODO.md`:

1. Remove issue 3 from `## High Impact`
2. Remove issues 4 and 6 from `## Medium Impact`
3. Add all three to `## Completed` section with status notes:

```markdown
### 3. Add task dependency support
The skill has no concept of blocked-by relationships between tasks. The lead manages this naturally, but a less experienced lead might assign tasks prematurely. Add guidance for using `addBlockedBy` in TaskCreate/TaskUpdate. **Status: done — added dependency bullet to lead.md.**

### 4. Unresponsive member protocol
No guidance on what to do when a member goes idle repeatedly without reporting. Suggested rule: "If a member goes idle 3x without progress, read their output files directly and reassign if stuck." **Status: done — added three-step idle protocol to lead.md.**

### 6. Rotation point tracking is implicit
The skill says "track points" but provides no persistence mechanism. Points reset every session. Add a `rotation_points` field to each member's status file so it persists across rotations and sessions. **Status: done — clarified as in-memory tally, reset on rotation. No persistence needed.**
```

- [ ] **Step 2: Commit**

```bash
git add skills/hip-kernel-team/TODO.md
git commit -m "docs: mark issues 3, 4, 6 as completed in TODO.md"
```
