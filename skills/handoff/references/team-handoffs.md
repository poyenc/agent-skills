# Multi-agent team handoffs

You reached this because your handoff roster was non-empty -- you spawned teammates this session and can still reach them via SendMessage. Each teammate holds private context (what it built, learned, and half-changed) that lives in *its* process, not yours, and a fresh session **cannot reconnect to them** -- they die with the old process. So the new lead must spawn *new* Agents (same names, types, roles) and feed each the context its predecessor held. That is what the per-teammate handoffs are for; without them the team starts cold even if your lead handoff is perfect.

The goal is unchanged -- make the fresh session resume as if nothing closed -- but "the session" is now the whole team. This guide is a *delta* on the main handoff passes (Pass 1 State, Pass 2 HOW), which you already have in context; it does not restate them.

## One handoff per agent, kept separate

Write one handoff file per agent that holds live context -- one for you (the lead) plus one per teammate. This separation is the thing that makes the team restorable: on resume, each respawned teammate reads *its own* file and reloads its own context, so no single file has to carry the whole team. Keep them as separate files; don't fold teammates into the lead file.

Because each teammate reloads itself from its own handoff, the lead **needn't read the teammate files** -- just know a seat exists and where its file lives, then route that path at respawn. Not reading them keeps the fresh boot lean (the whole point of splitting); skim one only if a small team genuinely needs it. Default: route without reading.

## Filenames: one shared stamp, one file per seat

Same location and stamp rule as a solo handoff (per-user dir, a fresh `<YYMMDD-HHMMSS>` each session), with two team additions:

    ${TMPDIR:-/tmp}/handoff-$(id -un)/<YYMMDD-HHMMSS>-handoff-<topic>-<seat>.md

- Add a **`-<seat>` suffix**: the lead uses `lead`, each teammate uses its name -- e.g. `...-handoff-vae-optim-lead.md`, `...-handoff-vae-optim-profiler.md`.
- **All files in the set share one stamp.** Generate it once at the top of the handoff and reuse it across every file you write this session -- don't call `date` per file, or `ls <stamp>-*` won't recover the set as one group.

## Step 1 -- collect one handoff per teammate

Before collecting, tell teammates to pause starting new work so nothing is half-changed while they summarize. Then SendMessage each live teammate this brief verbatim (fill the resolved path), so the skill stays self-contained even though teammates don't have it loaded:

> Write a handoff for your seat so your replacement in a fresh session resumes exactly where you are. Save it to `<resolved per-teammate path>`, overwriting if it exists. Capture: what you're mid-way through and the exact next action; the rules or constraints *I (the lead) gave you for this task* and *why* -- NOT standing global config from CLAUDE.md/AGENTS.md that the fresh session loads on its own (don't copy in house style, path/tool conventions, commit rules, etc.); decisions you made and their rationale -- still-binding choices, not finished steps (a finished step goes in your status/results, not into decisions); dead ends already ruled out; and the files/branch/commands your remaining work touches. Don't paste file contents that can be read directly. Strip secrets. Reply with only the path once written.

Collect the confirmed paths from their replies. If a teammate is unreachable or died, note that seat as needing a cold restart in your lead handoff rather than guessing its state.

## Step 2 -- record the team in your lead handoff

Your lead handoff is the normal one (Passes 1-2) plus a **Respawn the team** section so the fresh lead can rebuild the roster deterministically. Per seat capture:

- **Seat name** -- the Agent name to reuse, so SendMessage addressing and cross-references line up.
- **Agent type / model** -- the `subagent_type` (and model override, if any) it was spawned with.
- **Role in one line** -- what this seat owns, so the lead can brief it even if its handoff is thin.
- **Handoff path** -- the file from Step 1.
- **Isolation** -- worktree/branch/cwd it ran in, if any, so parallel editors don't collide again.

Also record team-wide structure that isn't per-seat, *as negotiated this session*: concurrency cap, who reports to whom, background/cron cadence -- captured with their *why*, and omitting ambient global config just as Pass 2's operating rules do (no delegate-by-default, spot-check/verify, don't-block). The teammate handoff paths belong in this Respawn section (they're respawn payloads), so you don't also need to list them in Pass 1 "State & references".

## Step 3 -- the fresh lead respawns and routes

The team kickoff prompt (below) points the fresh lead at the lead handoff. Its Respawn section then tells the lead, for each seat: spawn a new Agent with the recorded name and type, and in that Agent's opening prompt include this brief verbatim (fill the path):

> Read your own handoff file at `<resolved per-teammate path>` first, before anything else, then resume the work exactly from where it leaves off. Follow the operating rules and decisions in it as if given to you directly.

The lead routes each file to its seat, restoring the team in the fresh session exactly as it stood.

## Regenerating a team handoff

Same rule as solo: always regenerate from context -- never re-read the prior handoffs back -- and write a fresh stamped set for this session (a new `date +%y%m%d-%H%M%S`, shared across the new lead and teammate files). Don't let content accumulate: collapse finished seats to a line (or drop them), and keep only still-active seats as respawn targets.

## Finish: the team kickoff prompt

Use this variant instead of the solo one -- it steers the fresh lead to rebuild the team via the Respawn section:

```
========== COPY TO START NEXT SESSION ==========
Continue the work described in the lead handoff at <resolved-lead-path>.
Read it fully first before doing anything.
This handoff describes a team. Follow its "Respawn the team" section: for each seat, spawn a
new agent with the recorded name and agent type, and in that agent's opening prompt tell it to
read its own teammate handoff file first and resume from it. You generally don't need to read
the teammate files yourself -- each teammate reloads its own -- so route each path to its seat.
Follow the operating rules and decisions in the lead handoff as if given to you directly,
then pick up the task list where it leaves off.
===================== END ======================
```
