# Hip Kernel Team: Knowledge/Status Ownership and Rule Deduplication

## Problem

Two issues with the current hip-kernel-team skill:

1. **Knowledge/status file ownership is unclear.** The Recall
   Integration section assigns write access to multiple roles
   (Profiler writes measurements, Researcher writes findings), but
   members' work is temporary -- the Lead decides keep/revert. Members
   writing directly to knowledge files risks polluting them with
   findings that get reverted.

2. **Shared rules are copy-pasted across member templates.** Output
   Handling, Context Efficiency, Git Safety, and On Shutdown rules
   appear in `lead.md` (enforcement section) AND in each member
   template. The copies have drifted: inconsistent git rules per role,
   profiler adds extra rationale, researcher substitutes different
   rules entirely.

## Design

### 1. Only the Lead writes to knowledge.md and status.md

Members produce results in output files (`/tmp/<team>/<role>/`). The
Lead reads member output via subagents, makes keep/revert decisions,
then promotes verified results to `knowledge.md` and updates
`status.md`.

**File changes:**

- **`roles/lead.md` Recall Integration section** -- Rewrite to remove
  the per-role responsibilities table. Replace with:

  > Only you (the Lead) write to status.md and knowledge.md. Members
  > produce results in their output files. After a keep/revert
  > decision, promote verified findings to knowledge.md.
  >
  > Members read workflows.md for build/test/bench commands (injected
  > in their prompt via {{WORKFLOWS}}).

  Keep the directory layout documentation. Keep the "Without Recall"
  fallback section with "You maintain status.md and knowledge.md
  directly."

- **`roles/researcher.md`** -- Remove lines 128-130 (the "Write
  verified findings to the knowledge file" instruction and
  `{{KNOWLEDGE_FILE}}` / fallback path). The Researcher reports
  findings in output files and messages.

- **`roles/profiler.md`** and **`roles/implementer.md`** -- No change
  needed (they already have no knowledge.md write instructions).

- **`phases/spawn.md`** -- Remove `{{KNOWLEDGE_FILE}}` from the
  placeholder-to-source mapping table. No member template uses it.

### 2. Extract shared rules into roles/shared.md

Create `roles/shared.md` containing rules every teammate must follow.
This is injected into every teammate's prompt at spawn time.

**Content of `roles/shared.md`** (extracted from current duplicated
sections):

- **Output Handling** -- save all command output to
  `{{OUTPUT_DIR}}<desc>_NNN.txt 2>&1`, never pipe through filters,
  print the file path, read/analyze separately via Read or subagent,
  never print long output inline.

- **Context Efficiency** -- files < 100 lines read directly; 100-500
  use offset/limit; > 500 spawn Explore subagent; assembly files (.s)
  always via subagent.

- **Git & File Safety** -- never `git stash pop` or `git stash drop`
  (always `git stash apply`); backup before reverting (`cp file
  file.bak`); clean build artifacts before rebuilding.

- **On Shutdown** -- when Lead asks to prepare for rotation: save
  status to `.claude/teams/{{TEAM_NAME}}/status/<role>.md` (task ID,
  progress, key findings), confirm to Lead, approve shutdown_request.

- **First Actions** -- check TaskList for assigned tasks; wait for
  Lead to assign work.

**Changes to member templates** (`implementer.md`, `profiler.md`,
`researcher.md`):

- Remove all sections that moved to `shared.md` (Output Handling,
  Context Efficiency, Git & File Safety, On Shutdown, First Actions).
- Keep role-specific content only:
  - `implementer.md`: role description, compile-safety checklist
  - `profiler.md`: role description, assembly analysis pattern,
    benchmark analysis, register pressure analysis
  - `researcher.md`: role description, external code analysis pattern,
    compiler investigation pattern, findings report format

**Changes to `lead.md`:**

- The "Rules You Enforce on Members" section is replaced with a short
  paragraph: "Members receive shared rules in their prompt (from
  `roles/shared.md`). Watch for violations of: output handling (inline
  dumps instead of file paths), context efficiency (reading large files
  directly), git safety (stash pop/drop), and message efficiency (ack
  then done instead of one message)." This avoids restating the full
  rules while telling the Lead what to watch for.

**Changes to `phases/spawn.md`:**

- Add step: after reading the role template and before filling
  placeholders, read `roles/shared.md` and append its content to the
  member's prompt.

### 3. Template variable cleanup

| Variable | Change |
|---|---|
| `{{KNOWLEDGE_FILE}}` | Remove from `spawn.md` -- no member uses it |
| `{{STATUS_FILE}}` | Keep -- Lead still uses it |
| `{{OUTPUT_DIR}}` | Move to `shared.md` -- used in shared Output Handling |

### 4. Team-scope rule (already implemented)

The Lead's blacklist ("You do NOT: edit code, run builds...") has been
replaced with a team-scope rule: every teammate must be one of the
defined roles. The Lead may use subagents for coordination but never
spawns ad-hoc teammates outside the role definitions. This is already
in `lead.md` and does not need further changes.

### 5. Minor fixes

- **`lead.md` line 112**: Rename "Two-step shutdown" to "Rotation
  shutdown procedure" (it actually has 5 steps).
- **`lead.md` line 89**: Already changed to "Create investigation
  tasks for the team and propose next steps."

## Files to modify

| File | Action |
|---|---|
| `roles/shared.md` | **Create** -- shared rules for all members |
| `roles/lead.md` | Edit Recall Integration, edit Rules You Enforce |
| `roles/researcher.md` | Remove knowledge file write instructions, remove duplicated shared sections |
| `roles/profiler.md` | Remove duplicated shared sections |
| `roles/implementer.md` | Remove duplicated shared sections |
| `phases/spawn.md` | Add shared.md injection step, remove `{{KNOWLEDGE_FILE}}` |

## Verification

1. Grep for `KNOWLEDGE_FILE` across all skill files -- should only
   appear in `lead.md` (if at all) and `spawn.md` placeholder table
   (removed).
2. Grep for duplicated rule text (e.g., "Never pipe through", "git
   stash pop") -- should appear only in `shared.md` and `lead.md`'s
   enforcement summary.
3. Read each modified file end-to-end to check for internal
   consistency.
4. Verify `spawn.md` injection step produces correct combined prompts.
