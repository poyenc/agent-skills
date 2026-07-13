---
name: handoff
description: Compact the current conversation into a handoff document so a fresh agent can continue the work without losing context. Use when the user says "handoff", "hand off", "write a handoff", or otherwise asks to checkpoint or wrap up the current work so a new session can pick up seamlessly.
---

# Handoff

Write a handoff so a fresh agent resumes the work **exactly the way this session was running** -- same rules, same decisions, same next steps -- without the user re-explaining anything. It's a `--resume`: restore the *working setup*, not just the task.

A plain summary captures *state* -- WHAT was done and WHAT's next -- but drops the HOW: the rules negotiated mid-session, the decisions and their rationale, the dead ends already ruled out. So capture in two passes.

## Where to save

Save one self-contained file to the OS temp dir with consistent naming so it's findable: `${TMPDIR:-/tmp}/handoff-<short-kebab-topic>.md` (e.g. `handoff-auth-refactor.md`). Keep everything in this one file -- don't split content into separate files, which the next agent tends to skip.

## Pass 1 -- State (WHAT)

- **Objective** -- the goal in 1-2 sentences, and what "done" looks like.
- **Task list** -- done / in progress / not started. If a plan, todo list, PRD, or issue already tracks this, link it instead of copying.
- **State & references** -- key files (paths), branch, build/test/run commands, and external artifacts (PRs, docs, dashboards) by path or URL. Don't paste diffs or file contents the next agent can read directly.

## Pass 2 -- The HOW (what summaries lose)

Re-scan the conversation targeting these. Quote the user where exact phrasing matters, and capture each rule *with its why* so the next agent can judge edge cases instead of blindly obeying.

- **Operating rules / constraints** -- how the user wants work done, whether prescribed or prohibited: e.g. delegation strategy, async vs. synchronous execution, tooling and style preferences, and any hard boundaries. These are often stated once, in passing, and are the first thing a summary drops.
- **Decisions & rationale** -- the current choice and why, plus alternatives rejected, so settled questions aren't re-litigated. If the user reversed an earlier decision, record the final one and mark the old as reversed -- don't present it as active.
- **Workflow to resume** *(only if one was in use)* -- the operating structure to reconstruct: subagent team layout (roles, lead vs. workers, who does what), background/cron cadence, and any in-flight delegated work plus how to check on it.
- **Dead ends / gotchas** -- approaches already tried that failed, and what NOT to retry. High-value and almost always missing from summaries.
- **Suggested skills** -- only skills actually used or discussed this session, and when to invoke them. Never invent one; omit if none apply.

If a rule is uncertain, ask the user rather than guessing -- a wrong rule is worse than an absent one.

Strip API keys, passwords, tokens, and PII before saving.

## Finish: present the kickoff prompt

After writing the file, output a ready-to-paste prompt for the next session, wrapped in the exact markers below so the user can copy it cleanly and tell it apart from your own reply. Emit the resolved absolute path. Add no commentary between the markers.

```
========== COPY TO START NEXT SESSION ==========
Continue the work described in the handoff at <resolved-path>.
Read it fully first, including every file it references, before doing anything.
Follow the operating rules and decisions in it as if given to you directly.
Then pick up the task list where it leaves off.
===================== END ======================
```
