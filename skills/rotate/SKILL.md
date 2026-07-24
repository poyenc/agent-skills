---
name: rotate
description: Hot-swap a running teammate while the session stays live. Invoked by the main agent when it wants to replace a teammate for any reason - the skill does not assume a trigger. The fresh agent resumes the task exactly where the outgoing agent left off. Not user-invocable - the main agent is the only one who knows the teammate's SendMessage name.
---

# Rotate

Replace a running teammate without stopping the session. The fresh agent picks up exactly where the outgoing agent left off; other teammates continue uninterrupted.

## Procedure

### Step 1 - Request the rotation brief

Choose a writable path that includes the agent name to avoid collision, e.g. `/tmp/rotate-brief-<agent-name>.md`. Send:

```
SendMessage({
  to: "<agent-name>",
  message: "Write a rotation brief to <path>. Include: your current task and the exact next action, constraints with why, current decision and rationale, dead ends and why not to retry, key files and commands needed. Reply with the path when done."
})
```

### Step 2 - Wait for ack

Do not proceed until the outgoing agent confirms the file is written. If no ack arrives after a reasonable wait, proceed to Step 3 anyway - an unresponsive agent cannot improve the brief. If the brief is missing, reconstruct context from files and your own memory.

### Step 3 - Stop the outgoing agent

```
TaskStop({ task_id: "<agent-name>" })
```

### Step 4 - Spawn the fresh agent

Read the brief. Spawn:

```
Agent({
  name: "<same-name-as-outgoing>",
  subagent_type: "<same-type>",
  prompt: "<role context> + <full contents of the rotation brief>",
})
```

Use the same name so SendMessage routing is unchanged. Use the same `subagent_type` as the original spawn; if unknown, default to `general-purpose`.

Prepend role context before the brief: at minimum the agent's role description, who it reports to, and how to communicate. If the original prompt is gone, reconstruct the key role framing from your own context.

### Step 5 - Confirm resumption

The fresh agent's first message should state its next action. If it doesn't, send: "Read your rotation brief and state the next action you are taking."

## The brief format

The brief you receive should contain:

**Keep/drop test:** Keep what remaining work needs. Drop everything finished or superseded.

**Keep:**
- Current task - what it is and the exact next action
- Constraints and rules - each with *why* so the fresh agent can judge edge cases
- Active decision and rationale - settled choice or current candidate, and rejected alternatives
- Dead ends - what was tried and why not to retry it
- Key files, branch, commands needed to continue

**Drop:**
- Completed-step narrative - collapse the finished set to one line
- Intermediate results superseded by a later result - keep latest only
- Anything the fresh agent can read directly from files

Target: under 30 lines. Longer means accumulating, not distilling.
