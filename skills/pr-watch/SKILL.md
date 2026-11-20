---
name: pr-watch
description: >
  Watch a GitHub repository for pull requests matching the user's interest and have each one
  reviewed: this session becomes the supervisor, which scans the repository on a schedule and
  starts a lead agent per PR in a tab of its own herdr workspace; each lead uses the `pr-review-auto`
  skill and reports back when it finishes. Use when the user asks to set up, change, start, stop
  or check on a watcher, to watch a repo for PRs, to review PRs automatically on a schedule, or
  to change a watcher's interest criteria, schedule or lead settings. Trigger on "pr-watch",
  "/pr-watch", "PR watcher", "watch PRs", "auto review PRs", "configure pr-watch", "start the
  fmha watcher", "stop the watcher".
---

# pr-watch

```
/pr-watch <name>
```

This session becomes the supervisor of watcher `<name>`. In this file and in `prompts/`,
`pr-watch` means `scripts/pr-watch` in this skill's directory, run by its absolute path.

One watcher is one config, `~/.claude/pr-watch/<name>.yaml`, and one record of the PRs it has
handled, `~/.claude/pr-watch/<name>/record.yaml` (`$PR_WATCH_HOME` overrides `~/.claude/pr-watch`).
Take the watcher name from the request; if the user names none and exactly one config exists,
use it, otherwise ask.

## Before the first watcher on a repository

Every lead uses the `pr-review-auto` skill, which keeps its own config per repository (review team,
blocking threshold, dry run). The user must run `/pr-review-auto <owner>/<repo> <PR>` once per
repository first, which asks for that config and creates it. A lead started for a repository
without one stops at once and reports `needs-config`; the supervisor asks the user to do this
and retries the PR on the next fire. Remind the user of this when setting up a watcher.

## Configure

When `<name>` has no config, or the user asks to change one, read `prompts/configure.md` and
follow it: it asks the user one question at a time (each with a recommended value) and
validates a candidate config with `pr-watch validate <name>` before moving it into place.
`examples/fmha.yaml` is a complete example config.

## Start: `/pr-watch <name>`

1. If there is no config for `<name>`, configure it first (above).
2. Run `pr-watch validate <name>`; stop and report if it prints problems.
3. Remind the user that each repository needs its one-time `/pr-review-auto` setup (above).
4. Read `prompts/supervisor.md`. From now on this session is the supervisor and follows it.
5. Schedule the loop: run `/loop <every> pr-watch-fire <name> cli=<path>`, with `<every>` the
   config's `schedule.every` and `<path>` the absolute path of `scripts/pr-watch`. `/loop` runs
   the first fire at once; every fire renews the job before its 7-day expiry.

This session must run in a herdr pane (`HERDR_ENV=1`): each PR gets a tab in this session's
herdr workspace, and its lead reports `done` to this session's pane.

## Stop

Tell the supervisor session to stop. It deletes its loop job (CronList, then CronDelete the job
whose prompt starts with `pr-watch-fire <name>`) and opens no further PR; a lead already
running finishes and its result is recorded. Ending the session also ends the loop job, but
leaves a running lead's tab open.

## Check on a watcher

`pr-watch running <name>` shows the PR run in progress, and `pr-watch record <name>` prints the
record of PRs and their statuses.

## Review cap

`max_reviews_per_fire` in the config (integer 1 or more; default 4) is the most leads one fire
starts, which bounds token spend. `pr-watch fire-start <name>` opens each fire's count and
`pr-watch tab-open` refuses a lead once the count reaches the cap, so a supervisor that lost its
context cannot exceed it. The other interesting PRs stay recorded and queued, oldest first, for
the next fire. A lead that ends `busy` or `needs-config` gives its slot back. There is no "no
cap" value: set a large number to effectively lift it. The key can be edited while a watcher
runs: `tab-open` loads the config each time. A user-ordered retry of a stalled PR bypasses the
cap (`tab-open --ignore-cap`) and is not counted.

## Dry run

Dry run is a setting of the `pr-review-auto` skill, per repository. The record keeps, for each PR,
whether its last result was a dry run. After the user turns dry run off there, run
`pr-watch forget-dry-run <name>` (or ask the supervisor to): it clears the stored result of
every PR whose last result was a dry run, so each gets a real review on the next fire. Merged,
closed and stalled PRs keep theirs, and a pending decision stays.

## How it works

On each fire the supervisor (this session, lean: it never reads PR content) re-reads the config,
renews its loop, skips the fire while a lead is still running (and flags the PR `stalled` after
`max_pr_duration`), opens the fire's review count (`max_reviews_per_fire`), starts a Haiku scanner subagent that classifies new PRs against `interest`
and returns the PR numbers to process, then opens one tab per PR, one PR at a time, until the cap. Each tab
holds a lead (`orchestrator` persona, `team.lead` settings; the key is optional and defaults to
harness `claude`, model `Claude-Sonnet-5.5[1m]`, effort `high`, each key replaced on its own, and a
changed harness needs a model) started with
`<invoke> <owner>/<repo> <PR> --checkout <checkout> --supervisor <pane> [--interest <text>] [--decision <text>]`,
where `<invoke>` is `/pr-review-auto` for claude and `/skill:pr-review-auto` for pi (`team.lead.invoke`
overrides it). The lead reviews the PR with the `pr-review-auto` skill and messages the supervisor
`done <PR> <result> head=<sha|none> dry_run=<true|false> [summary]`; the supervisor closes the
tab, records the result, shows escalations to the user and stores the user's answer for the next
lead on that PR. This skill itself makes no GitHub writes, keeps no per-PR notes and handles no
branches.

## Prerequisites

- This session runs Claude Code in a herdr pane (`HERDR_ENV=1`): `/loop`, the scanner subagent
  and the PR tabs need it.
- `gh` authenticated with write access to the repository; `pr-watch validate` checks it.
- The lead's harness installed (`claude`, or `pi`).
- The lead persona `orchestrator/system-prompt.md` under `persona_dir`.
- The `pr-review-auto` skill installed for the lead's harness, and set up once for the repository.
- A dedicated worktree for `checkout`: every lead discards its uncommitted and untracked files.

## CLI reference

Every subcommand takes the watcher name first. The supervisor and the scanner run most of them;
the user runs `validate`, `running`, `record`, `clear-scan-mark` and `forget-dry-run`.

| Command | Purpose |
|---|---|
| `pr-watch validate <name>` | Check the config: name matches the file, durations parse (`schedule.every` under 7d), repo reachable with write access, `checkout` is a worktree whose origin is the repo, supervisor harness is claude, lead harness installed with model and effort (defaults applied), scanner model set, lead persona file exists. Exit 1 with one line per problem. |
| `pr-watch running <name>` | JSON: the PR run in progress, its elapsed minutes, whether it is over `max_pr_duration`. |
| `pr-watch record <name>` | Print the record (PR statuses, `last_scanned_pr`) as YAML. |
| `pr-watch clear-scan-mark <name>` | Forget `last_scanned_pr` so all open PRs are classified again. |
| `pr-watch set-status <name> <pr> <status>` | Set a PR's status: new, reviewed, escalated, approved, merged, closed, stalled. |
| `pr-watch decide <name> <pr> <text>` | Store the user's answer to a PR's escalation in the record; the next lead for that PR gets it with `--decision`. |
| `pr-watch forget-dry-run <name>` | Clear the stored result (status, `updated_at`, `head_sha`) of every PR whose last result was a dry run, except merged, closed and stalled ones, so it is reviewed again; a pending decision stays. |
| `pr-watch pending <name> [--limit N]` | JSON: the next batch (up to `--limit`, default 10, and at most 20000 printed characters; lowest numbers first) of new open PRs to classify, and whether more are waiting (scanner). |
| `pr-watch commit-classified <name>` | Read classification JSON on stdin; record interesting PRs and raise `last_scanned_pr` (scanner). |
| `pr-watch queue <name>` | JSON `{"process": [...]}`: the PR numbers to process; records PRs found merged or closed (scanner, supervisor). |
| `pr-watch finish <name> <pr> <result> --head <sha\|none> --dry-run <true\|false>` | Record a lead's `done`: reviewed, approved, escalated, no-action, not-interesting (removes the PR), merged, closed, needs-config, busy (both keep the PR as it was, so the next fire retries it, and give back their slot of the review cap); stores the reviewed head and the dry-run flag (supervisor). |
| `pr-watch fire-start <name>` | Open this fire's review count (once per fire, before the scan); prints `{"started_at": ..., "max_reviews_per_fire": N}` (supervisor). |
| `pr-watch tab-open <name> <pr> [--ignore-cap]` | Open the PR's tab in this session's herdr workspace, start its lead and send it the start message, and count the PR against `max_reviews_per_fire`. Once the cap is reached it opens nothing and exits 1 (`cap reached`; the PR stays queued for the next fire). `--ignore-cap` skips the check and the count (supervisor). |
| `pr-watch tab-close <name> <pr>` | Close the PR's tab; a tab herdr no longer knows counts as closed (supervisor). |
