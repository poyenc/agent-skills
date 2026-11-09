---
name: pr-review
description: >
  Review one GitHub pull request with a herdr agent team: this session becomes the lead, starts a
  reviewer and an architect in panes next to it, verifies their findings, posts them under the
  user's own gh account (inline blocking threads, one non-blocking comment, approval when every
  blocking thread is addressed), and on later runs follows up on its own threads. Use when the
  user asks to review a PR, to follow up on a PR reviewed earlier, to answer an escalation on a
  PR, or to set up or change the review settings of a repository. Trigger on "pr-review",
  "review PR", "review this pull request", "follow up on PR", "/pr-review".
---

# pr-review

```
/pr-review <owner>/<repo> <PR> [--checkout <path>] [--supervisor <target>] [--interest <text>] [--decision <text>] [--include-merged] [--full-review]
```

This session becomes the lead of a one-PR review team: read and follow `prompts/lead.md` (in
this skill's directory) with the invocation's arguments. In this file and in `prompts/`,
`pr-review` means `scripts/pr-review` in this skill's directory, run by its absolute path.

- `--checkout`: the git worktree to review in (default: this session's working directory). It
  must be the root of a git worktree whose `origin` is `<owner>/<repo>` (GitHub https, `git@`
  or `ssh://` URL), used by nothing else; `pr-review checkout` refuses any other path and
  changes nothing there. Each run detaches
  it, runs `git reset --hard` and `git clean -fdx`, which deletes every uncommitted and
  untracked file in it (ignored files too), fetches the PR into branch `pr-review/<PR>` and
  checks that commit out, detached, so no worktree of the clone holds the branch.
- `--supervisor`: the herdr pane ID of an agent that started this run; the lead reports its
  result there (`done <PR> <result> head=<sha|none> dry_run=<true|false> [summary]`) instead of
  to the user, and never asks the user anything.
- `--interest`: plain-language criteria, given only by a supervisor; the lead first checks the
  PR against them and stops with `not-interesting` when it clearly does not match.
- `--decision`: the user's answer to an earlier escalation on this PR; the lead records it in
  the PR's notes and applies it.
- `--include-merged`: review a merged or closed PR anyway, as a preview. Without it, the lead
  stops at once on such a PR. With it, the run goes on as for an open PR, but every write is
  recorded in the PR's notes, never posted (the CLI refuses to write to a PR that is not open),
  the run reports `dry_run=true`, never approves, and deletes the PR's branch at the end.
- `--full-review`: run a full first review even when the PR already has notes or review threads of
  ours (for example comments posted by hand). It requires `dry_run: true` in the repository
  config and otherwise refuses, because it would duplicate the existing review comments. The
  existing GitHub threads are not imported, changed or replied to; any existing notes file for
  the PR is replaced by a fresh one; every write is recorded in the notes, and the run reports
  `dry_run=true`. Combines with `--include-merged` and `--interest`.

The first run on a repository without a config asks the user for one (`prompts/configure.md`);
a run started with `--supervisor` reports `needs-config` instead. To change a repository's
config later, follow `prompts/configure.md`. `examples/config.yaml` is a complete example. The `team` block is optional: the reviewer
defaults to harness `pi`, model `amd-gateway/gpt-6.1-sol`, effort `high`, and the architect to
harness `claude`, model `Claude-Opus-5.5[1m]`, effort `high`; a key set in the config replaces
only that key, and overriding a role's harness requires setting its model too.

A new config has `dry_run: true`: the lead writes would-be comments into the PR's notes file
and changes nothing on GitHub. Read a first few notes before setting `dry_run: false`.

## Prerequisites

- A herdr pane (`HERDR_ENV=1`, `HERDR_PANE_ID` set): the team starts in panes split from it.
- `gh` authenticated with write access to the repository (comments, resolve, approve).
- The harness of each team role installed (`claude`, or `pi`).
- The persona prompt files under `persona_dir` (`orchestrator`, `reviewer`, `architect`, each
  with `system-prompt.md`).

`pr-review validate <owner>/<repo>` checks all of these except the herdr pane.

## Files

Under `~/.claude/pr-review/` (`$PR_REVIEW_HOME` overrides it):

- `<owner>/<repo>/config.yaml`: the repository config.
- `<owner>/<repo>/<PR>/`: per-PR state: `notes.md` (review state, threads, escalations, log),
  `reports/<reviewed-sha>/` (the first review's final reports and critiques), `runs/` (task
  files and reports of the current run), `lock` (held while a run works on the PR). With
  `dry_run: true` it is `<owner>/<repo>-dry-run/<PR>/` instead, so turning dry run off starts
  clean.

## Branches

The local branch `pr-review/<PR>` is deleted when a run ends with the PR approved, and when a
run finds the PR merged or closed. To delete the leftover branches of PRs that are merged,
closed or approved, run `pr-review cleanup <owner>/<repo> --checkout <path>`; it prints the PR
numbers whose branches it deleted and touches no other branch. Every run that checked out its
PR also runs `cleanup` on its checkout as its last step; a failure there does not change the
run's result.

## CLI reference

Every subcommand except `notify` and `member-close` needs the repository config and exits 3
when there is none; exit 1 is any other error (including a config that cannot be read), exit 2
a bad repository argument.

| Command | Purpose |
|---|---|
| `pr-review validate <owner>/<repo>` | Check the repository config: values, `gh` access with write permission, team harnesses installed, persona files present. Exit 1 with one line per problem. |
| `pr-review paths <owner>/<repo> <pr>` | JSON: the PR's `pr_dir`, `notes`, `runs` and `reports` paths; creates `runs/` and `reports/`. |
| `pr-review decide <owner>/<repo> <pr> <text>` | Write the user's decision into the `## Decision` section of the PR's notes. |
| `pr-review review-state <owner>/<repo> <pr>` | JSON: `last_reviewed_head`, `saved_reports` and `status` from the notes' review state. |
| `pr-review pr-state <owner>/<repo> <pr>` | JSON: the PR's `state` (OPEN, MERGED, CLOSED), `head`, `author`, `is_own`. |
| `pr-review checkout <owner>/<repo> <pr> --checkout <path>` | Refuse unless the checkout is a worktree root whose `origin` is `<owner>/<repo>`; detach, reset and clean it, fetch the PR into `pr-review/<pr>`, check that commit out detached, print the head SHA. |
| `pr-review drop-branch <owner>/<repo> <pr> --checkout <path>` | Delete the local branch `pr-review/<pr>` if present (detaching first when it is current). |
| `pr-review cleanup <owner>/<repo> --checkout <path>` | Delete the `pr-review/<N>` branches of merged, closed or approved PRs; print the deleted PR numbers (exit 1 when a branch could not be checked or deleted, after printing). Every run that checked out its PR runs it at its end. |
| `pr-review lock <owner>/<repo> <pr> --holder <id>` | Take the PR's lock: `{"locked": true}`, or `{"busy": true, "holder", "since"}` while another run holds it; a lock older than `lock_stale_after` is taken over. |
| `pr-review unlock <owner>/<repo> <pr> --holder <id>` | Release the PR's lock if `<id>` holds it. |
| `pr-review gh <owner>/<repo> <pr> <action> [thread_id] [--commit <sha>]` | GitHub action with the agent header and dry-run handling (a write to a PR that is not open, or whose state cannot be read, is recorded in the notes like a dry run, never posted): threads, post-review, comment, reply, resolve, unresolve, approve; body or payload on stdin; post-review and approve need `--commit <reviewed head>`, and approve skips (`head-moved`) when the PR's head is no longer that commit, and (`own-pr`) on the user's own PR. |
| `pr-review spawn <owner>/<repo> <pr> reviewer\|architect` | Start a team member in a pane split from the caller's pane (reviewer to the right, architect below), in the caller's working directory; print its agent name. |
| `pr-review member-close <agent>` | Close a team member's pane. |
| `pr-review notify <target> <text>` | Send a message to a herdr agent name or pane ID; needs no config. |
