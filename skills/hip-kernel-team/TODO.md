# hip-kernel-team Skill Issues

## High Impact

## Medium Impact

### 5. Flexible team size
The skill always assumes a full roster (lead + implementer + profiler + researcher). Sometimes only 1-2 members are needed. Add support for "solo mode" (1 member) or "pair mode" (2 members) to save resources.

## Low Impact

## Completed

### 3. Add task dependency support
The skill has no concept of blocked-by relationships between tasks. The lead manages this naturally, but a less experienced lead might assign tasks prematurely. Add guidance for using `addBlockedBy` in TaskCreate/TaskUpdate. **Status: done — added dependency bullet to lead.md.**

### 4. Unresponsive member protocol
No guidance on what to do when a member goes idle repeatedly without reporting. Suggested rule: "If a member goes idle 3x without progress, read their output files directly and reassign if stuck." **Status: done — added three-step idle protocol to lead.md.**

### 6. Rotation point tracking is implicit
The skill says "track points" but provides no persistence mechanism. Points reset every session. Add a `rotation_points` field to each member's status file so it persists across rotations and sessions. **Status: done — clarified as in-memory tally, reset on rotation. No persistence needed.**

### 1. Kill the bootstrap subagent
Each member spawns an Explore subagent to read status files on boot (+10% context for zero unique value). The lead already has this context — should inline a 5-line state summary directly in the spawn prompt instead. **Status: done — context-bloat reduction.**

### 2. Merge lead.md and operate.md
Both contain lead instructions with overlap. `lead.md` says "injected into main conversation" but `spawn.md` tells the lead to read `operate.md`. Consolidate into one file. **Status: done — context-bloat reduction.**

### 7. Communication rules are decorative
Generated as a table per spawn but never enforced. Members message whoever they want. Replace with a single sentence: "Report to lead; DM peers when directly relevant." Remove the generation step from spawn.md. **Status: done — context-bloat reduction.**

### Extract shared content from role templates
Role templates embedded ~120 lines of duplicated content each. Extracted into `shared/briefing-template.md` — agents read it on demand instead of carrying it in their spawn prompt. **Status: templates updated but reverted by linter; needs re-application.**

### 9. Task decomposition pipeline templates
When a task requires multiple team roles, the lead had no standard pipeline templates. Added `phases/decompose.md` with 4 pipeline patterns (Optimize, Experiment, Investigate, Hotfix), decision framework for iteration/re-entry, escape hatch rules, handoff protocol, and pipeline proposal protocol. One reference line added to `lead.md`. **Status: done.**

### 8. Initial context injection for teammates
Teammates didn't receive SessionStart hook output (directives, user profile, project config). Added `{{INITIAL_CONTEXT}}` placeholder filled from `.claude/teams/<name>/initial-context.md`. Lead copies hook output verbatim via shared instructions in `phases/write-initial-context.md` (called by setup step 7b and resume step 3b). Includes line-count verification via subagent and fallback for missing hooks. **Status: done — v2: extracted shared file, added verification, removed exclusion note.**
