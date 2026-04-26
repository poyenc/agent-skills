# hip-kernel-team Context-Bloat Reduction

**Problem:** Each spawned team member consumes ~15% context before processing
its first user prompt. Three independent sources contribute to this bloat.

**Scope:** Issues 1, 2, 7 from `skills/hip-kernel-team/TODO.md`. Operational
improvements (issues 3-6) are deferred to a follow-up plan.

**Approach:** Sequential, one commit per fix. Each change is independently
testable by measuring prompt size.

---

## Fix 1: Kill the Bootstrap Subagent

**Root cause:** Every role template instructs the member to spawn an Explore
subagent on boot to read status files. On a fresh team, these files don't
exist — the subagent reads nothing and wastes ~10% context. On resume, the
lead already has this context and can pass it inline.

### Changes

**Remove from role templates** (`implementer.md`, `profiler.md`,
`researcher.md`):
- Delete the `## Bootstrap` section (the `Agent({...Explore...})` block and
  surrounding text)
- In `## First Actions`, remove step 1 ("Bootstrap context via subagent") and
  renumber remaining steps

**Remove from `operate.md`:**
- Delete the `### Member Bootstrap` section (lines 170-185)

**Add to `spawn.md`** (new step between current steps 4 and 5):

> **Step 4.5: Prepare inline state summary**
>
> For each member being spawned, read `{{STATUS_FILE}}` and check if
> `.claude/teams/<team-name>/status/<role>.md` exists. Compose a compact
> summary (under 10 lines) of: current state, recent results, active tasks,
> key findings, and any rotation handoff notes. If no status files exist,
> use: `"Fresh team -- no prior state. Wait for task assignment."`

**Add `{{CURRENT_STATE}}` placeholder:**
- Add to the placeholder table in `spawn.md` step 5:

  | `{{CURRENT_STATE}}` | Inline state summary prepared in step 4.5 |

- Add to each **member** role template (`implementer.md`, `profiler.md`,
  `researcher.md`), after `## Environment & Workflows`:

  ```markdown
  ## Current State

  {{CURRENT_STATE}}
  ```

  The lead does NOT get this placeholder — the lead is the one preparing
  the summaries.

### Validation

- Fresh spawn: members should NOT spawn any subagents before receiving their
  first task
- Resume spawn: members should have state context inline in their prompt
  without spawning subagents

---

## Fix 2: Merge operate.md into lead.md

**Root cause:** `roles/lead.md` and `phases/operate.md` both describe lead
behavior with significant duplication. The lead reads both files, paying
context cost twice for the same instructions.

### Merge plan

`roles/lead.md` is the merge target. `phases/operate.md` is deleted after
merge.

| operate.md section | Action |
|---|---|
| Task Management (7-14) | Drop -- already in lead.md with task-role matching |
| Iteration Budget (22-27) | Drop -- duplicate of lead.md:49-57 |
| Decision Loop (29-35) | Drop -- duplicate of lead.md:60-65 |
| When All Tasks Done (38-44) | Drop -- duplicate of lead.md:68-75 |
| Status Updates (46-52) | **Merge** -- add after Decision Loop in lead.md |
| Member Rotation (55-77) | Drop -- lead.md:79-94 covers this |
| Lead Rotation (79-87) | Drop -- duplicate of lead.md:96-101 |
| Operational Rules (92-134) | **Merge** -- add as "Rules You Enforce on Members" at bottom of lead.md |
| Recall Integration (138-168) | **Merge** -- add as "Recall Integration" section in lead.md |
| Member Bootstrap (170-185) | Drop -- removed by Fix 1 |

### Changes to spawn.md

Step 9 changes from:
> Read `${CLAUDE_SKILL_DIR}/phases/operate.md` and follow the Lead operating
> instructions for the rest of the session.

To:
> Follow the Lead instructions in `roles/lead.md` for the rest of the session.

### Validation

- `phases/operate.md` no longer exists
- `roles/lead.md` contains all unique content from both files
- No section appears twice in lead.md
- `spawn.md` references only lead.md, not operate.md

---

## Fix 3: Simplify Communication Rules

**Root cause:** `spawn.md` step 6 generates a role-pair communication table
(~15 lines) and injects it via `{{COMMUNICATION_RULES}}` into every member
prompt (~12 lines each). These rules are never enforced -- members message
whoever they want. Role-specific DM guidance already exists in each role
template's opening section.

### Changes

**In each role template** (`implementer.md`, `profiler.md`, `researcher.md`,
`lead.md`):

Replace:
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

**In `spawn.md`:**
- Remove step 6 ("Generate communication rules") entirely (lines 46-62)
- Remove `{{COMMUNICATION_RULES}}` from the placeholder table in step 5
- Renumber remaining steps (7 becomes 6, 8 becomes 7, etc.)

### Validation

- No role template contains `{{COMMUNICATION_RULES}}`
- `spawn.md` has no communication rules generation step
- Each role template has the hardcoded one-liner under `## Communication`

---

## Files Modified

| File | Fix | Change |
|---|---|---|
| `roles/implementer.md` | 1, 3 | Remove Bootstrap section, hardcode comm rules, add Current State placeholder |
| `roles/profiler.md` | 1, 3 | Same as above |
| `roles/researcher.md` | 1, 3 | Same as above |
| `roles/lead.md` | 2, 3 | Absorb operate.md content, hardcode comm rules |
| `phases/operate.md` | 2 | Deleted |
| `phases/spawn.md` | 1, 3 | Add state summary step, remove comm rules generation, remove bootstrap reference, update lead.md reference |

## Execution Order

1. Fix 1 (bootstrap) -- touches role templates + operate.md + spawn.md
2. Fix 2 (merge) -- touches lead.md + operate.md (delete) + spawn.md
3. Fix 3 (comm rules) -- touches all role templates + spawn.md

Each fix is one commit. Order matters: Fix 1 must run before Fix 2 because
Fix 1 removes the bootstrap section from operate.md, and Fix 2 then merges
the remaining operate.md content into lead.md and deletes operate.md.
