---
name: handoff
description: Compact the current conversation into a handoff document so a fresh agent can continue the work without losing context. Use when the user says "handoff", "hand off", "write a handoff", or otherwise asks to checkpoint or wrap up the current work so a new session can pick up seamlessly. If you spawned teammates via the Agent tool this session, read references/team-handoffs.md for the extra steps -- a plain handoff loses them.
---

# Handoff

Write a handoff so a fresh agent resumes the work **exactly the way this session was running** -- same rules, same decisions, same next steps -- without the user re-explaining anything. It's a `--resume`: restore the *working setup*, not just the task.

A plain summary captures *state* -- WHAT was done and WHAT's next -- but drops the HOW: the rules negotiated mid-session, the decisions and their rationale, the dead ends already ruled out. So capture in two passes.

## Roster: solo or team?

Did you spawn teammates this session via the Agent tool who are still reachable via SendMessage and whom you want restored next session? Idle or waiting teammates still count -- "idle" is a state, not a departure; one-shot subagents that already returned (Explore, research) and background shell jobs do not, since they hold no context to restore.

- **No** -- this is a **solo** handoff: just your own file. Continue below.
- **Yes** -- this is a **team** handoff: one file per agent, and the process differs. **Read `references/team-handoffs.md` and follow it** before writing -- a plain solo handoff would write only your own file and silently lose every teammate's context, the worst outcome this skill can produce.

## Where to save

Save to a **per-user directory** in the OS temp dir (`mkdir -m 700 -p`) so handoffs don't collide on a shared machine, with a **leading timestamp** so files sort chronologically: `${TMPDIR:-/tmp}/handoff-$(id -un)/<YYMMDD-HHMMSS>-handoff-<topic>.md` -- stamp from `date +%y%m%d-%H%M%S`, fresh each handoff (e.g. `/tmp/handoff-alice/260722-143005-handoff-auth-refactor.md`). Keep everything self-contained in this one file. (Teammate files add a seat suffix; see the reference.)

## What to keep, what to drop

One test governs every section below: **keep what the remaining work still needs; collapse or drop what's finished or superseded.**

- **Keep:** active rules (with *why*), dead ends (with *why not to retry*), the current decision + rationale, and the current state/result.
- **Drop:** completed-step narrative -- collapse the whole finished set to *at most one line* -- and any state a later step replaced. Keep the current value; if how it changed over time genuinely helps the next agent, record that trajectory in one place only, never restated across sections.

When regenerating over a prior handoff (you're chaining sessions), that file is already in your context -- **don't re-read it**. Regenerate and *replace*, don't append: the file should get *shorter* as work completes. If it grew, you're accumulating.

## Pass 1 -- State (WHAT)

- **Objective** -- the goal in 1-2 sentences, and what "done" looks like.
- **Task list** -- done / in progress / not started. If a plan, todo list, PRD, or issue already tracks this, link it instead of copying.
- **State & references** -- key files (paths), branch, build/test/run commands, and external artifacts (PRs, docs, dashboards) by path or URL. Don't paste diffs or file contents the next agent can read directly. List only what the *remaining* work needs, so the next session's startup fan-out stays bounded.

## Pass 2 -- The HOW (what summaries lose)

Re-scan the conversation targeting these. Quote the user where exact phrasing matters, and capture each rule *with its why* so the next agent can judge edge cases instead of blindly obeying.

- **Operating rules / constraints** -- how the user wants work done, *negotiated this session*: the caps, boundaries, and preferences set here (often stated once in passing -- the first thing a summary drops). Omit standing global config the fresh session reloads on its own (CLAUDE.md/AGENTS.md: delegate-by-default, don't-block, commit/style conventions) -- copying it bloats the handoff and misframes ambient rules as session decisions.
- **Decisions & rationale** -- the still-binding choice or the candidate under consideration, with its why and alternatives rejected, so settled questions aren't re-litigated. If the user reversed an earlier decision, record the final one and mark the old as reversed.
- **Workflow to resume** *(only if one was in use)* -- background/cron cadence, and any in-flight delegated work plus how to check on it.
- **Dead ends / gotchas** -- approaches already tried that failed, and what NOT to retry. High-value and almost always missing from summaries.
- **Suggested skills** -- only skills actually used or discussed this session, and when to invoke them. Never invent one; omit if none apply.

If a rule is uncertain, ask the user rather than guessing -- a wrong rule is worse than an absent one. Strip API keys, passwords, tokens, and PII before saving.

## Finish: self-review, then the kickoff prompt

Before presenting the prompt, re-read the file you just wrote against the keep/drop test: did you keep every fact that still matters (active rules, dead ends, decision rationale, current state) and drop everything finished or superseded, pasting nothing the next agent can re-read for itself and no ambient global config? Fix it if not.

Then output a ready-to-paste prompt for the next session, wrapped in the exact markers below so the user can copy it cleanly. Emit the resolved absolute path. Add no commentary between the markers. (If your roster had teammates, use the team kickoff variant from the reference instead.)

```
========== COPY TO START NEXT SESSION ==========
Continue the work described in the handoff at <resolved-path>.
Follow the operating rules and decisions in it as if given to you directly, without proactively reading the files it references -- open each one only when a task step actually needs it.
Then pick up the task list where it leaves off.
===================== END ======================
```
