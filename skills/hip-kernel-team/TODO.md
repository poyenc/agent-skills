# hip-kernel-team Skill Issues

## High Impact

### 3. Add task dependency support
The skill has no concept of blocked-by relationships between tasks. The lead manages this naturally, but a less experienced lead might assign tasks prematurely. Add guidance for using `addBlockedBy` in TaskCreate/TaskUpdate.

## Medium Impact

### 4. Unresponsive member protocol
No guidance on what to do when a member goes idle repeatedly without reporting. Suggested rule: "If a member goes idle 3x without progress, read their output files directly and reassign if stuck."

### 5. Flexible team size
The skill always assumes a full roster (lead + implementer + profiler + researcher). Sometimes only 1-2 members are needed. Add support for "solo mode" (1 member) or "pair mode" (2 members) to save resources.

### 6. Rotation point tracking is implicit
The skill says "track points" but provides no persistence mechanism. Points reset every session. Add a `rotation_points` field to each member's status file so it persists across rotations and sessions.

## Low Impact

## Completed

### 1. Kill the bootstrap subagent
Each member spawns an Explore subagent to read status files on boot (+10% context for zero unique value). The lead already has this context — should inline a 5-line state summary directly in the spawn prompt instead. **Status: done — context-bloat reduction.**

### 2. Merge lead.md and operate.md
Both contain lead instructions with overlap. `lead.md` says "injected into main conversation" but `spawn.md` tells the lead to read `operate.md`. Consolidate into one file. **Status: done — context-bloat reduction.**

### 7. Communication rules are decorative
Generated as a table per spawn but never enforced. Members message whoever they want. Replace with a single sentence: "Report to lead; DM peers when directly relevant." Remove the generation step from spawn.md. **Status: done — context-bloat reduction.**

### Extract shared content from role templates
Role templates embedded ~120 lines of duplicated content each. Extracted into `shared/briefing-template.md` — agents read it on demand instead of carrying it in their spawn prompt. **Status: templates updated but reverted by linter; needs re-application.**
