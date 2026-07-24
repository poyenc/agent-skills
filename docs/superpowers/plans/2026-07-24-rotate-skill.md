# Rotate Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write a self-contained `rotate` skill the main agent invokes to hot-swap one running teammate while the session stays live.

**Architecture:** Single Markdown file `skills/rotate/SKILL.md`. No sub-files, no references directory. Fully self-contained — installs and works without any other skill. A companion check script (`skills/rotate-workspace/checks/skill.sh`) enforces a word cap to prevent bloat.

**Tech Stack:** Markdown skill file. Bash check script.

## Global Constraints

- `skills/rotate/SKILL.md` is the only committed artifact. The check script lives in `skills/rotate-workspace/` and stays local/uncommitted.
- The skill must be self-contained — no references to `handoff` or any other skill.
- Not user-invocable — the main agent is the only invoker.
- Absolute paths, no `cd`; capture full command output to files.

---

### Task 1: Write SKILL.md, verify it passes the word cap, commit

**Files:**
- Create: `skills/rotate/SKILL.md`
- Create (local only, do not commit): `skills/rotate-workspace/checks/skill.sh`

**Interfaces:**
- Produces: `skills/rotate/SKILL.md` — a complete, self-contained skill the main agent can follow verbatim.

- [ ] **Step 1: Create the workspace directory**

```bash
mkdir -p skills/rotate-workspace/checks
```

- [ ] **Step 2: Write `skills/rotate/SKILL.md` with exactly this content**

```markdown
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
```

- [ ] **Step 3: Measure the word count and record it as W**

Run:
```bash
wc -w skills/rotate/SKILL.md
```
Record the number as `W`. Call the cap `ceil(W * 1.05)`.

Example: if `W` = 360, cap = `ceil(360 * 1.05)` = 378.

- [ ] **Step 4: Write `skills/rotate-workspace/checks/skill.sh`**

Replace `<CAP>` with your computed cap value:

```bash
#!/usr/bin/env bash
set -euo pipefail
SKILL="skills/rotate/SKILL.md"
words=$(wc -w < "$SKILL")
[ "$words" -le <CAP> ] || {
  echo "FAIL: skill bloated ($words > <CAP> words) -- compact before committing"
  exit 1
}
echo "PASS: $words words (<= <CAP>)"
```

- [ ] **Step 5: Run the check**

```bash
bash skills/rotate-workspace/checks/skill.sh
```

Expected output: `PASS: <N> words (<= <CAP>)`

If it fails, trim the skill and re-run until it passes.

- [ ] **Step 6: Commit only the skill file**

```bash
git add skills/rotate/SKILL.md
git status
```

Confirm `git status` shows only `skills/rotate/SKILL.md` staged. Nothing from `rotate-workspace/`.

```bash
git commit -m "feat: add rotate skill for hot-swapping teammates"
```

- [ ] **Step 7: Verify**

```bash
git show --stat HEAD
```

Expected: exactly one file — `skills/rotate/SKILL.md`.

---

## Self-Review

**Spec coverage:**
- Single file, self-contained, no references → Task 1 Step 2. ✓
- Main-agent-invoked only → frontmatter description. ✓
- 5-step procedure (request → ack → stop → spawn → confirm) → Steps 1-5 in skill body. ✓
- Same name on fresh agent → Step 4 note. ✓
- Briefing format inlined (keep/drop, target length) → "What the outgoing agent writes" section. ✓
- Word cap enforced mechanically → Task 1 Steps 3-5. ✓
- Commit only the skill file → Task 1 Steps 6-7. ✓

**Placeholder scan:** No TBD, no TODO, no "handle edge cases". `<CAP>` is a computed value with a worked example — not a placeholder. ✓

**Type consistency:** N/A — no code types. Section names used in the check script (`skills/rotate/SKILL.md`) match the file path defined in Step 2. ✓
