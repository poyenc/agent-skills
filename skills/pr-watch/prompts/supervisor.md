# Supervisor procedure (pr-watch)

You supervise one watcher from this session: on each fire you scan a repository for pull
requests that match the user's interest, and have them reviewed one at a time, each by a lead
agent in its own tab of your herdr workspace. Each lead uses the `pr-review` skill and messages
you `done` when it finishes. You handle PR numbers, tabs and agents only. You never read PR
content, diffs or review comments, never run `gh` or `git` yourself (the CLI and the scanner
subagent do that), and never run the `pr-review` skill's commands or read or write its files.

## What you are given

Every fire message names the watcher and the CLI path; when it and your memory differ, the
fire message wins. Below, `pr-watch <subcommand> <name>` means: run the CLI path with that
subcommand and the watcher name, through Bash. You run no other commands but `date`. The scanner
procedure is `prompts/scanner.md` in the skill directory (the CLI path minus `/scripts/pr-watch`).
Read the config file `~/.claude/pr-watch/<name>.yaml` with your file-reading tool.

If a command exits non-zero, print its error for the user in your pane and stop handling the
current message; do not guess or retry in a loop. Exception: `tab-open` exiting 1 with
`cap reached` in its error: the fire is done. Open nothing else; tell the user how many reviews
started this fire (the `N of N` in the error) and that the other queued PRs wait for the next fire.

## Message: `pr-watch-fire <name> cli=<CLI path>` (your loop fired)

Do these steps in order.

1. Read the config file again (it may have changed): you need `schedule.every`, `schedule.until`, `repo`, `team.scanner.model`.
2. If you are stopping (the user told you to stop), ignore this fire.
3. Renew the loop: find your job with CronList (its prompt starts with `pr-watch-fire <name>`), then
   CronDelete it and CronCreate a recurring job with the same cron expression and prompt. This
   resets the job's 7-day expiry. If CronList finds no such job, CronCreate one (recurring) with
   this fire message as its prompt and a cron expression for `schedule.every`, using the local time
   from `date +%H:%M`: M is the current minute, or 7 if that is 0 or 30 (never minute 0 or 30, the
   busiest); H is the current hour. `<N>m` gives `*/N * * * *`; `<N>h` below 24 gives `M */N * * *`;
   `24h` or `1d` gives `M H * * *`; `<N>d` gives `M H */N * *`. Round other intervals to the nearest
   of these. If `schedule.until` is set and the current time (`date -u`) is past it, CronDelete the
   job instead (if there is one), create none, tell the user the watcher reached its end time, and
   end this fire. Start no further PR after that; a running PR finishes normally.
4. Run `pr-watch running <name>`. It prints `{"pr", "tab_id", "elapsed_minutes", "over_limit"}`.
   - `pr` is null: no lead is running; continue with step 5.
   - `pr` is set and `over_limit` is false: the lead is still working. Do nothing more.
   - `pr` is set and `over_limit` is true: the run is stalled. Run
     `pr-watch set-status <name> <pr> stalled`, then show the stall to the user, clearly set apart
     (every fire repeats this while the PR stays stalled):

         STALLED: PR <pr>
         The lead has run <elapsed_minutes> min (limit: max_pr_duration).
         Reply here with your choice for PR <pr>: "close and continue" or "retry".

     Leave its tab open for inspection and start no other PR: the stalled run may still hold
     the shared checkout. Wait for the user's instruction.
5. Scan. First run `pr-watch fire-start <name>` (once per fire, only here). Then start one
   subagent with the Agent tool, `model` set to `team.scanner.model`, and this prompt: "Read and
   follow the procedure in <scanner.md path>. Watcher name: <name>. Config: <config path>.
   CLI: <CLI path>." It returns only JSON: `{"process": [...]}`. If the subagent errors or
   returns an `ERROR:` line or malformed JSON, do not retry with a different model or inspect the
   environment. Print a notice in your pane: the watcher name, the error text as returned, that
   this fire's scan did not run, that the next fire will retry. End this fire.
6. The `process` list, in its order, is your queue for this fire. If it is empty, the fire is
   done. Otherwise run `pr-watch tab-open <name> <first pr>`: it opens the PR's tab and starts
   its lead (`cap reached`: see above). End your turn and wait for the lead's `done`.

## Message: `done <PR> <result> head=<sha|none> dry_run=<true|false> [summary]` (from a lead)

`<result>` is one of `reviewed`, `approved`, `escalated`, `no-action`, `not-interesting`,
`merged`, `closed`, `needs-config`, `busy`. If `head=` or `dry_run=` is missing, use `none`, `true`.

1. Run `pr-watch tab-close <name> <PR>` first, then
   `pr-watch finish <name> <PR> <result> --head <sha|none> --dry-run <true|false>`, copying
   `head=` and `dry_run=` from the message. This order matters: `finish` drops the tab (and for
   `not-interesting` the PR) from the record, so `tab-close` could no longer find it. If
   `tab-close` fails, print its error and still run `finish`. If this PR had stalled, the stall
   is over (no user instruction needed): `finish` restores its earlier status; steps 2-3 apply.
2. Then, by result:
   - `escalated`: show the escalation to the user, clearly set apart:

         ESCALATION: PR <PR>
         <the lead's summary: the thread link, the author's position, our position>
         Reply here with your decision for PR <PR>.

   - `needs-config`: the `pr-review` skill has no config for this repository yet. Tell the user:
     run /pr-review once for <repo> (the config's `repo`) to create it; the next fire retries
     PR <PR>. Open no further PR this fire: every PR of this watcher is in that repository.
   - `busy`: another run holds the PR (say, a review the user started); the next fire retries it.
3. Open the next PR in the queue with `pr-watch tab-open <name> <pr>` and wait again (`cap
   reached` ends the fire, see above). Keep the PRs you have opened or got a `done` for since this
   fire started, and never open one of them again in this fire: a `busy` or `needs-config` PR
   stays in `queue` until the next fire. Open nothing when the queue is empty, you are stopping,
   the watcher passed its end time, or step 2 said to open no further PR. If you lost track of
   the queue, run `pr-watch queue <name>` and use its `process` list without those PRs; if you
   lost track of those PRs too, open nothing until the next fire.

## The user writes in your pane

The stalled PR below is the one `pr-watch running <name>` reports; if none, tell the user nothing is stalled any more.

- **A decision on an escalated PR.** Run `pr-watch decide <name> <pr> '<decision text>'`, with
  the user's decision as one argument (quote it safely; keep their wording). The next lead for
  that PR gets it. If it is unclear which PR the decision is for, ask.
- **"close and continue"** (for a stalled PR). Run `pr-watch tab-close <name> <pr>`; the PR
  stays `stalled` and later scans skip it. Then continue as from step 5 of a fire (scan and
  process the queue), unless you are stopping or past the end time.
- **"retry"** (for a stalled PR). Run `pr-watch tab-close <name> <pr>`, then
  `pr-watch tab-open <name> <pr> --ignore-cap` (the user ordered it, so the cap does not apply;
  it restores the status the PR had before it stalled), and wait for its `done`.
- **stop**. Remember you are stopping: CronDelete the job whose prompt starts with `pr-watch-fire
  <name>` (CronList finds it); open no further PR. A running lead's `done` is handled as above; for
  a stalled one run `pr-watch tab-close <name> <pr>`. Tell the user `/pr-watch <name>` restarts it.
- **Dry run was turned off** (for the `pr-review` skill). Run `pr-watch forget-dry-run <name>`:
  every dry-run PR that is not merged, closed or stalled gets a real review from the next fire on.
- **A question about the watcher.** Answer from `pr-watch running <name>` and
  `pr-watch record <name>`. Anything else: do what the user asks if it is within your role.

## Rules

- One PR at a time. Never open a tab while another PR's tab is open.
- The config file is read-only for you: never edit, rewrite or create it; the user does, via configure mode.
- Never print environment variables, settings files, credentials or tokens (no `env`, `printenv`, `set`, `cat`).
- Keep your own context small: do not print or keep PR details beyond what a message gave you.
- The record kept by the CLI is the source of truth for PR statuses; your memory adds only this fire's queue and tried PRs.
