# Rotate Skill Design

**Date:** 2026-07-24
**Goal:** A self-contained skill the main agent follows to hot-swap one running teammate while the session stays live.

---

## Problem

When the main agent wants to replace a running teammate — for any reason — there is no defined procedure. Without one, context is lost and the fresh agent starts cold with no knowledge of the task it's inheriting.

## Scope

- Hot-swap **one teammate** per invocation. Main agent loops if rotating multiple.
- Session stays live: other teammates and the main agent continue uninterrupted.
- **Main-agent-invoked only.** The main agent is the only one who knows the teammate's `SendMessage` name. The skill is not user-invocable.
- Independent of any specific team skill (hip-kernel-team, etc.) — works for any `Agent()`-spawned teammate.
- Does not overlap with `handoff` — `handoff` is full session shutdown; `rotate` is a hot-swap with the session continuing.

---

## Design

### File structure

Single file: `skills/rotate/SKILL.md`. No references directory, no sub-files. Fully self-contained — installs and works without any other skill installed.

### Trigger

The main agent invokes this skill whenever it wants to replace a running teammate. The reason is not the skill's concern.

### Procedure

Five steps, executed in order:

**Step 1 — Request the rotation brief**

Main agent chooses a path for the rotation brief (any writable temp path of its choice). Sends:

```
SendMessage({
  to: "<agent-name>",
  message: "Write a rotation brief to <path> covering everything the next agent needs to resume your current task. Reply with the path when done."
})
```

**Step 2 — Wait for ack**

Do not proceed until the outgoing agent replies confirming the file is written.

**Step 3 — Stop the outgoing agent**

```
TaskStop({ task_id: "<agent-name>" })
```

**Step 4 — Spawn the fresh agent**

```
Agent({
  name: "<same-name>",
  subagent_type: "<same-type>",
  prompt: "<contents of the rotation brief>",
  ... // model at main agent's judgment
})
```

Same name so `SendMessage` routing is unchanged for the rest of the team.

**Step 5 — Fresh agent resumes**

The fresh agent reads its opening prompt (the brief) and picks up the task where the outgoing agent left off.

---

## Rotation Brief Format

The outgoing agent writes this. The skill instructs it on what to include.

**Keep/drop test:** Keep what the remaining work still needs. Drop everything finished or superseded.

**Keep:**
- Current task — what it is and the exact next action
- Constraints and rules — with *why*, so the fresh agent can judge edge cases
- Active decision and rationale — the current candidate or settled choice, and alternatives already rejected
- Dead ends — what was tried and why not to retry it
- Key files, branch, commands needed to continue

**Drop:**
- Narrative of completed steps — collapse the entire finished set to at most one line
- Intermediate results replaced by a later result — keep the latest, drop what it superseded
- Anything the fresh agent can read directly from files or code

The brief should be shorter than a session handoff — just enough to resume one task. If it grew longer than ~30 lines, it is accumulating, not distilling.

---

## What This Skill Does Not Cover

- Deciding *when* to rotate — that is the main agent's judgment, driven by whatever signal it has
- Rotating all teammates at once — main agent invokes this skill once per agent
- Roster tracking or spawn parameter bookkeeping — main agent uses its own context for model/type
