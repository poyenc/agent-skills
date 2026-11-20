---
name: pr-review
description: Use when you are the lead agent and are asked to review a pull request by number ("review PR 108", "/pr-review 108"), to run the next review round after the author pushed fixes, or to consolidate reviewer and architect reports. It drives a reviewer agent and an architect agent that are already running in your herdr workspace: triage with care marks by PR type, facts-only findings, a findings ledger kept across rounds and sessions, and one-by-one posting through post-review. Prefer it over code-review when such a council is available; it never starts agents and never posts without the owner's word. Not for the reviewer or architect agents themselves, and not for a quick one-session review of a diff.
---

# PR review (lead)

You triage a PR, drive two already-running council agents (a reviewer and an architect),
consolidate their reports, and help the owner post only what is worth posting. You do not start,
rotate, or replace council agents. Repository-specific rules (comment templates, scratch paths,
design documents) come from the target repository's CLAUDE.md and docs, not from this skill.

Invocation: `/pr-review <PR number>`. The number arrives as the skill's argument; if it is missing,
ask the owner which PR. The same command starts round one or a later round: step 2 decides which
from the PR's ledger.

Standing rules:
- Review facts, never wording (see Facts only).
- Nothing is posted, approved, or merged without the owner's explicit word.
- Never message the PR's author. A PR with merge conflicts is skipped (step 2).

## 1. Name yourself and find the council

1. If you have no herdr agent name, give yourself `pr-lead` (`herdr agent rename`, pane
   `$HERDR_PANE_ID`); if a live agent already has it, use `pr-<workspace id lowercase>-lead`.
   Briefs name you as the callback target, so do this first.
2. Run `scripts/find-council` (next to this file). It finds the reviewer and architect by launch
   command (`--system-prompt-file .../agents/<role>/system-prompt.md`) in your own workspace only;
   agent names do not matter. Exit 2 means a role has none or several: stop and ask the owner. Also
   stop and ask if either agent is not `idle` and interactive-ready.
3. Give an unnamed council agent `<your name minus -lead>-reviewer` or `-architect`. If that name is
   taken, ask the owner.
4. From now on address every agent by name through the `herdr-kit:message` skill (non-blocking;
   replies arrive as your next turn).

## 2. Gate

`gh pr view <N> --json baseRefOid,headRefOid,mergeable,mergeStateStatus`. If `mergeable` is
`CONFLICTING` or `mergeStateStatus` is `DIRTY`, the PR conflicts: skip it and tell the owner (the
owner asks the author to resolve conflicts). `mergeable` is `UNKNOWN` while GitHub is still
computing it (a PR list often shows it right after a push): query again before deciding, and ask
the owner only if it is still `UNKNOWN` after a few tries. Otherwise note the branch you are on
(`git rev-parse --abbrev-ref HEAD`), then `gh pr checkout <N>`; `gh pr checkout` moves your worktree
onto the PR branch, so switch back to the noted branch when you finish or stop reviewing this PR.
Always use explicit shas, never a local main branch.

Look for the PR's ledger (`references/reports-and-ledger.md`): none means round one, otherwise
a later round (step 7).

## 3. Triage

Follow `references/triage-checklists.md`: derive intent from the code, check the description's
freshness, classify each file by type, and write the half-page PR brief with the care marks.

## 4. Round one

Send `references/round-one-brief.md`, filled in, to both agents in parallel. Each reviews the whole
PR through its own lens; do not assign areas.

## 5. Completeness gate (you, no worker)

Compare each report with the changed-file list and your care marks. A file or mark with no
disposition goes back to the council now; this is the only full review, and late additions are
what stop rounds from converging.

## 6. Consolidate

Write the consolidated review per `references/reports-and-ledger.md`, nothing dropped. Spot-check
council claims against the repo and label the rest as claims. Save the round files and open the
ledger. Items reported as wording or renames go in their own "wording only" section, never as
findings or comments.

## 7. Later rounds

After the author pushes, send `references/later-round-brief.md`: revalidate open findings, review
only the delta since the previous head, never re-raise declined, deferred, or posted items. Show the
owner any "correction to an earlier round" separately. Then consolidate as in step 6 and update the
ledger.

## 8. Post

Use the `post-review` skill; its validation subagent always runs. One item at a time, highest risk
first, the owner decides each and sees the draft, and you post only on an explicit "post it".
Post only real defects or stale statements this PR introduced. Merge items with one cause; skip
pre-existing issues and anything outside the PR's scope. Record each decision in the ledger
(posted with link, declined with the reason, deferred). Any handoff note you write names the
PR's ledger path.

## Facts only

Reportable: a statement in a comment, document, PR description, or name that is false, stale, or
contradicts the code; any other defect with a concrete consequence. Not reportable, and the
council must not propose it: phrasing, tone, structure, terminology preference, a rewrite of a
true statement, "could be named better". A name is an issue only if it states something false.
This overrides the wording and naming checks in the council's own prompts.
