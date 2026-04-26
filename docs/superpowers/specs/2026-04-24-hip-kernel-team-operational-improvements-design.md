# hip-kernel-team Operational Improvements

**Problem:** The lead's operating instructions lack guidance for task
dependencies, unresponsive members, and rotation point tracking.

**Scope:** Issues 3, 4, 6 from `skills/hip-kernel-team/TODO.md`. Issue 5
(flexible team size) is deferred to a separate spec.

**Approach:** Extend existing sections in `roles/lead.md` inline. No new
H2 sections. ~15 lines total added.

---

## Issue 3: Task dependency support

**Location:** `roles/lead.md`, `## Your Role` bullet list (after
task-role matching bullet, before "Approve or reject").

**Add one bullet:**

```markdown
- Use `addBlockedBy` when creating tasks with dependencies. Do not
  assign a task that has unresolved blockers — check `blockedBy` in
  TaskList output before assigning.
```

---

## Issue 4: Unresponsive member protocol

**Location:** `roles/lead.md`, new `### Unresponsive Members` subsection
under `## Member Rotation` (after the "Two-step shutdown" numbered list,
before `## Your Own Rotation`).

**Add:**

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

---

## Issue 6: Clarify rotation point tracking

**Location:** `roles/lead.md`, `## Member Rotation` section, after the
existing sentence "Rotate at the configured threshold (default: 3
points)."

**Add one sentence:**

```markdown
Keep a mental tally per member — reset to 0 after rotation.
```

No file persistence needed. Points are tracked in-memory by the lead
and reset naturally when a member is rotated (new agent, fresh context).

---

## Files Modified

| File | Fix | Change |
|---|---|---|
| `roles/lead.md` | 3, 4, 6 | Add dependency bullet, unresponsive member subsection, tracking clarification |

## Execution Order

All 3 fixes touch `roles/lead.md` only. They can be applied in any order.
Single commit for all 3.
