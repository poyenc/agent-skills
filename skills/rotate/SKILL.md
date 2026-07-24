---
name: rotate
description: Hot-swap a running teammate while the session stays live. Invoked by the main agent when it wants to replace a teammate for any reason — the skill does not assume a trigger. The fresh agent resumes the task exactly where the outgoing agent left off. Not user-invocable — the main agent is the only one who knows the teammate's SendMessage name.
---

# Rotate

Replace a running teammate without stopping the session. Other teammates and the main agent continue uninterrupted. The fresh agent picks up exactly where the outgoing agent left off.

## Procedure

### Step 1 — Request the rotation brief

Choose a writable path for the brief (any temp path of your choice). Send:

```
SendMessage({
  to: "<agent-name>",
  message: "Write a rotation brief to <path>. Include: your current task and the exact next action, constraints with why, current decision and rationale, dead ends and why not to retry, key files and commands needed. Reply with the path when done."
})
```

### Step 2 — Wait for ack

Do not proceed until the outgoing agent replies confirming the file is written.

### Step 3 — Stop the outgoing agent

```
TaskStop({ task_id: "<agent-name>" })
```

### Step 4 — Spawn the fresh agent

Read the brief at the confirmed path. Spawn:

```
Agent({
  name: "<same-name-as-outgoing>",
  subagent_type: "<same-type>",
  prompt: "<full contents of the rotation brief>",
})
```

Use the same name so SendMessage routing is unchanged for the rest of the team. Match the outgoing agent's model and type if you remember them; otherwise use sensible defaults.

### Step 5 — Confirm resumption

The fresh agent's first message should state its next action. If it doesn't, send: "Read your rotation brief and tell me the next action you are taking."

## What the outgoing agent writes (the brief)

When you ask the outgoing agent to write the brief (Step 1), it follows this format.

**Keep/drop test:** Keep what the remaining work still needs. Drop everything finished or superseded.

**Keep:**
- Current task — what it is and the exact next action
- Constraints and rules — each with *why*, so the fresh agent can judge edge cases
- Active decision and rationale — the settled choice or current candidate, and alternatives already rejected
- Dead ends — what was tried and why not to retry it
- Key files, branch, commands needed to continue

**Drop:**
- Completed-step narrative — collapse the entire finished set to at most one line
- Intermediate results replaced by a later result — keep the latest, drop what it superseded
- Anything the fresh agent can read directly from files or code

Target length: under 30 lines. If it grew longer, it is accumulating, not distilling.
