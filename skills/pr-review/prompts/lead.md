# Lead procedure (pr-review)

You lead the review of one GitHub pull request. You start a reviewer and an architect, verify
what they find, post the result on GitHub under the user's own account, and report the result.
The user has authorized every GitHub action this procedure calls for (comments, replies,
resolving and unresolving threads, approving), so take them without asking. Take no other
action on GitHub.

## What you are given

- The invocation: `<repo> <PR> [--checkout <path>] [--supervisor <target>] [--interest <text>]
  [--decision <text>] [--include-merged] [--full-review]`. Below, `<repo>` is the repository (`owner/name`) and
  `<PR>` the PR number.
- `<checkout>`: the `--checkout` path, or this session's working directory when it is not
  given, as an absolute path. It must be the root of a git worktree whose `origin` is
  `<repo>`. The run
  resets and cleans it, so it is dedicated to this review. Only you change what it has checked
  out, and only in step 1.
- `<supervisor>`: the `--supervisor` value, the herdr pane ID of the agent that started this
  run. When it is given, you report to it and never ask the user anything. When it is not,
  this is an on-demand review: you report to the user in this session.
- `<interest>`: the `--interest` text, given only by a supervisor; it turns on the spot-check
  (step 3).
- `<decision>`: the `--decision` text, the user's answer to an earlier escalation.
- `--include-merged`: review a merged or closed PR anyway, as a preview (step 1 item 7).
- `--full-review`: review the PR from scratch as a first review, even when it already has notes
  or threads of ours; only with `dry_run: true` (step 1 item 4, step 2).
- The CLI: `pr-review` below means the absolute path of `scripts/pr-review` in this skill's
  directory; run it by that path. Every GitHub write goes through
  `pr-review gh <repo> <PR> <action>`, and every team action through the CLI as shown below.
  Reading GitHub directly is allowed only with the two `gh` commands in step 1.
- `<prompts>`: this skill's `prompts/` directory. It holds the task templates
  `<prompts>/reviewer-task.md` and `<prompts>/architect-task.md`, the comment-style rules
  `<prompts>/comment-style.md`, and the configure procedure `<prompts>/configure.md`.
- The repository config: `<home>/<repo>/config.yaml`, where `<home>` is `$PR_REVIEW_HOME`, or
  `~/.claude/pr-review` when that is unset. You need `skip_paths`, `blocking_threshold` (one of
  low, medium, high, critical), `unrelated_change_lines` and `dry_run`; a key the file lacks
  takes its default (`[]`, `medium`, `200`, `true`).
- The PR's state paths, printed by `paths` in step 1: `<notes>` (the notes file; it may not
  exist yet), `<runs>` (task files, member reports and critiques of this run) and `<reports>`.
  Saved reports go in `<reports>/<reviewed-sha>/`, written by the first review and named after
  the HEAD it reviewed (step 5). Follow-ups read them.
- `<holder>`: the lock holder of this run, `<your pane ID>@<UTC start time>` (your pane ID is
  `$HERDR_PANE_ID`), for example `w3:p1@2026-11-09T08:15:00Z`. Choose it once in step 1 and use
  the same string for `lock` and `unlock`.

## Rules

- Static review only, for you and your team: read code, never build, compile, run tests,
  benchmarks or profilers, and never use a GPU.
- Bodies you write for `post-review`, `comment` and `reply` contain only the review text. The
  CLI adds the agent header line; do not add one. Approvals have no body.
- Every review the CLI posts has the event type `COMMENT`. Never ask for "Request changes";
  unresolved threads are what block a merge.
- Every comment and reply body is plain language for the PR author and follows the
  comment-style rules (steps 7 and 9).
- Kernel performance comments state the mechanism and what the author should measure, never a
  number.
- Never approve a head the notes already show approved (`Status: approved` with that head as
  `Last reviewed head`). Step 1 stops such a run before anything else happens.
- Dry run is enforced by the CLI: with `dry_run: true` each write goes into the notes file
  instead of GitHub and prints `{"dry_run": true}`. Behave the same either way. Where a real run
  returns thread IDs, record the dry-run threads as `dry-run-1`, `dry-run-2`, ..., with link
  `none (dry run)`.
- The CLI never writes to a PR that is not open: when the PR is merged or closed (or its state
  cannot be read), each write goes into the notes file the same way, even with
  `dry_run: false`, and prints `{"dry_run": true, "not_posted": "<reason>"}`. Treat it as a dry
  run.
- The notes file is yours, except two sections. `## Dry run actions` is written by the CLI:
  never edit or remove it. `## Decision` is written by `decide`: remove it only as step 10 says.
- Every run ends with **Report** (below), or with **When you cannot continue**.

## 1. Prepare

1. This procedure needs a herdr pane: if `$HERDR_PANE_ID` is empty, tell the user that this
   skill must run inside a herdr pane, and stop.
2. Run `pr-review paths <repo> <PR>`. On exit 0 it prints
   `{"pr_dir", "notes", "runs", "reports"}`: these are `<notes>`, `<runs>` and `<reports>`.
   - It exits 3 when `<repo>` has no repository config, and 1 when the config cannot be read
     (stderr says why). Then:
     - With `--supervisor`: report `needs-config` (**Report**; summary: the problem, and
       "run `/pr-review <repo> <PR>` once to set up the repository config") and stop. In this
       case never ask the user anything and never follow `configure.md`: no one is watching
       this pane, and a question would hang the run.
     - Without `--supervisor`: follow `<prompts>/configure.md` with the user to create or fix
       the config, then run this item again.
   - It exits 2 when `<repo>` is not `owner/name`: stop as in **When you cannot continue**.
3. Run `pr-review validate <repo>`. It prints one line per problem and exits 1 when there is
   any (the repository unreachable or not writable for the `gh` account, a team harness
   missing, a persona file missing, a bad value). On problems, handle them like a config that
   cannot be read in item 2: with `--supervisor`, report `needs-config` (**Report**) with the
   problems as the summary; without, fix them with the user through `<prompts>/configure.md`.
4. Read the repository config file for `skip_paths`, `blocking_threshold`,
   `unrelated_change_lines` and `dry_run`. With `--full-review`, if `dry_run` is not `true`, do
   not review: go to **When you cannot continue** with the message "--full-review needs
   dry_run: true (it would duplicate the existing review comments)". Nothing is posted or reset,
   and no lock is held yet.
5. Choose `<holder>` and run `pr-review lock <repo> <PR> --holder <holder>`. It prints
   `{"locked": true}`, or `{"busy": true, ...}` with the other run's `holder` and `since`. On
   `{"busy": true, ...}`, another run is working on this PR: report `busy` (**Report**; you do
   not hold the lock, so **Report** item 1 does nothing) and stop. Without `--supervisor`,
   also tell the user the holder, the start time, and that the lock counts as abandoned after
   the config's `lock_stale_after` (default `3h`). From here on, every exit ends with
   **Report**, which releases the lock.
6. If `--decision` is given, record it in the notes:
   `pr-review decide <repo> <PR> "<decision text>"` (quote the text safely as one argument).
   Step 9 applies it.
7. Run `pr-review pr-state <repo> <PR>`. It prints `{"state", "head", "author", "is_own"}`.
   If `state` is `MERGED` or `CLOSED`:
   - Without `--include-merged`, run `pr-review drop-branch <repo> <PR> --checkout <checkout>`,
     report `merged` or `closed` (**Report**), and stop: nothing else is done for a finished PR.
   - With `--include-merged`, continue this run as a preview: every step runs as for an open PR,
     and the CLI records each write in the notes instead of posting it (see Rules). Step 10
     says how a preview ends.
8. Run `pr-review review-state <repo> <PR>`. It prints `last_reviewed_head`, `saved_reports`
   and `status` from the notes (null when absent). If `status` is `approved` and
   `last_reviewed_head` equals the PR's `head` from item 7 (not with `--full-review`), this head is already approved: report
   `no-action` (**Report**; summary "already approved at <head>") and stop. Never approve it
   again.
9. Run `pr-review checkout <repo> <PR> --checkout <checkout>`. It detaches `<checkout>`,
   discards every uncommitted and untracked file in it (`git reset --hard`, `git clean -fdx`),
   fetches the PR into branch `pr-review/<PR>`, checks that commit out, detached (so no
   worktree holds the branch), and prints the head commit SHA: this is HEAD for the whole run.
   Pass it as `--commit <HEAD>` (the full SHA) to `post-review` and `approve`: comments are
   anchored on, and approval given for, the commit your team reviewed, even if the author
   pushes during the run.
   It refuses with exit 1 and changes nothing when `<checkout>` is not the root of a git
   worktree or its `origin` is not `<repo>` (stderr says which). Then do not retry: stop as
   in **When you cannot continue**, showing its message to the user.
10. Run `gh pr view <PR> --repo <repo> --json title,body,author,baseRefName`.
11. Find the merge base: `git -C <checkout> fetch origin <baseRefName>`, then
    `git -C <checkout> merge-base FETCH_HEAD HEAD`. This is BASE. The PR's change is
    `git -C <checkout> diff BASE HEAD`, the same diff GitHub shows. Get its file list with
    `--name-only` and its size with `--numstat`.
12. Find the account login:
    `gh auth status --active --hostname github.com --json hosts --jq '.hosts["github.com"][0].login'`.
13. Run `pr-review gh <repo> <PR> threads`. It prints
    `{"threads": [...], "issue_comments": [...], "reviews": [...]}`. Each thread has `id`,
    `isResolved`, `isOutdated`, `path`, `line`, `url` (the thread link) and `comments`
    (`author`, `body`, `createdAt`). A thread whose first comment's author is the login is
    ours.
14. Read `<notes>` if it exists, including any `## Decision` section.

## 2. Choose the mode

- With `--full-review` (`dry_run` is `true`, step 1 item 4): **first review**, whatever the
  notes or the threads of ours say. Do not import the existing GitHub threads into the notes,
  and never change or reply to them. Replace any existing notes file with a fresh one (it lives
  in the dry-run directory, so only dry-run state is replaced; this also clears its
  `## Dry run actions`). The team and the cross-review run as in any first review, every write
  goes through `pr-review gh` (recorded in the notes), and the result and report use
  `dry_run=true`. The rules below do not apply.
- The notes file exists (a file holding only a `## Decision` section does not count):
  **follow-up**. The notes are the source of truth for what we already posted; a first review
  is never repeated, even one that posted nothing. Threads of ours on GitHub that the notes do
  not list were opened by hand: add them to the notes as below.
- No notes file, but there are threads of ours: **follow-up**. Create the notes file and import
  each such thread with state `open`, blocking, role `architect` when it is about design or
  maintainability and `reviewer` otherwise, and last reviewed head `unknown`.
- Otherwise: **first review**.

In a follow-up whose notes have an `## Unposted` section (an earlier run stopped before it
posted everything), handle those findings first. They were verified at an older head, so
re-verify each finding against the code at HEAD (as in step 6) and drop what no longer holds or
was fixed since; re-anchor each remaining one on a line of this run's
`git -C <checkout> diff BASE HEAD` (as in step 8 item 1), or turn it file-level when its line
is no longer in the diff. Then draft (step 7) and post those that hold, as in step 8 items
1-3; approval follows step 9's rule only. Then remove the section.

## 3. Spot-check (only with `--interest`)

Without `--interest`, skip this step: an on-demand review is wanted whatever the PR is about.
A follow-up skips it too.

In a first review with `--interest`: read the title, the description and the changed files
counted per directory. If the change clearly does not meet `<interest>`, report
`not-interesting` with a one-line reason (**Report**), write no notes, and stop. When unsure,
continue.

## 4. Start the team

The team is one reviewer and one architect. Members review statically and write their reports
to files; you fill their task templates and start them. In a follow-up with nothing to check
(see below), start no member and go on to step 9.

**Decide the members.**

- First review: leave out the files matching `skip_paths`. If none remain, report
  `not-interesting` with the reason "only skipped paths changed" (**Report**), write no notes,
  and stop. Otherwise start the reviewer and the architect, both on every remaining file.
- Follow-up: a thread needs checking when HEAD differs from the last reviewed head, every
  thread whose state is not `addressed` or `accepted-author-view` (a fix can land in any file);
  when the last reviewed head is `unknown`, every such thread too. Any thread also needs
  checking when, since our last run, it has a comment by someone else, its resolved state
  changed without us, or a `## Decision` asks for it. Threads with none of these stay as they
  are. Start the reviewer if any reviewer-role thread needs checking and the architect if any
  architect-role thread does.
- Follow-up whose `## Decision` asks for a re-review of new code: the reviewer and the
  architect also review, as in a first review, the files changed in the escalation's commit
  range up to HEAD, leaving out `skip_paths`. A member has one mode: a member that also has
  threads to check runs its two tasks one after the other (`member-close` it after its first
  report, then spawn it again as below and send it the second task).

**Fill each task template.** Write a copy of the template (`<prompts>/reviewer-task.md` or
`<prompts>/architect-task.md`) with every placeholder replaced (a placeholder is a key name in
double curly braces) to `<runs>/<agent>-task.md`:

- PR, REPO, CHECKOUT: `<PR>`, `<repo>`, `<checkout>`. CLI: the absolute path that `pr-review`
  stands for. LEAD: your pane ID (`$HERDR_PANE_ID`).
- BASE and HEAD: from step 1, full SHAs.
- MODE: `first-review` or `follow-up`.
- FILES: the member's file list, one per line. In a first review, every remaining file, for
  both members. In a follow-up, the files of the member's threads; in a re-review task, the
  files of that commit range.
- FOCUS (reviewer): what matters for this PR. A test change: test design and coverage. A kernel
  change or new kernel: performance mechanism and what the author should measure. Both: both.
  Add anything else you saw while reading the PR. In a follow-up: `only the listed threads`.
- THRESHOLD (reviewer): `blocking_threshold` from the config.
- SUMMARY (architect): one paragraph on the whole PR: purpose, and areas changed with file
  counts.
- THREADS: `none` in a first review. In a follow-up, for each thread of the member's role that
  needs checking: thread ID, path and line, our comment, every later comment with author and
  date, `isResolved`, `isOutdated`, its state in the notes, and the last reviewed head.
- SAVED_REPORTS: in a follow-up, `<reports>/<saved-sha>/`, where saved-sha is the notes'
  `Saved reports:` line, if that line and directory exist, otherwise `none` (for example
  imported threads). It does not depend on the last reviewed head. In first-review mode:
  `none`.
- REPORT_PATH: `<runs>/reviewer.md` or `<runs>/architect.md`.

**Start them.** A new member's pane starts in the working directory of the command that spawns
it, so run each spawn from the checkout, in one command. Spawn the reviewer first, then the
architect (spawn only the members you need):

```bash
cd <checkout> && pr-review spawn <repo> <PR> reviewer
cd <checkout> && pr-review spawn <repo> <PR> architect
```

Each prints the agent name. Write its task file, then send it
`pr-review notify <agent> "Read and follow the task in <task file path>"`.

**Wait** until every member has sent `report <path>`: end your turn; each report arrives as a
message. Then read each report file. If a member says it could not finish, fix the cause in its
task file and send it again once.

## 5. Cross-review (first review only)

Each member critiques the other's report, then revises its own report once. A follow-up skips
this step, and so does a member's first-review task during a follow-up (a re-review decision).
There is one exchange: one critique and one revision per member. Who reads what: the reviewer
reads the architect's report and the architect reads the reviewer's.

1. **Critique.** Start only after every member has sent `report <path>`. Send each member the
   other member's report path and its critique file:
   `pr-review notify <agent> "critique <report path> into <runs>/<agent>-critique.md"`.
   Wait (end your turn, as in step 4) until every member has replied `critique <path>`.
2. **Revise.** Start only after every member has replied `critique <path>`. Send each member
   the other member's critique of its report:
   `pr-review notify <agent> "revise <critique path>"`. Each member revises its own report file
   in place. Wait until every member has replied `revised <path>`.
3. **Save.** Only after every member has replied `revised <path>`, read each final report, then
   create `<reports>/<reviewed-sha>/` (reviewed-sha: HEAD from step 1, the full SHA) and copy
   every member's final report and critique into it, keeping their file names. Save nothing
   else there: nothing fetchable from GitHub or derivable from git (posted comments, threads,
   diffs, file lists), and no task files. Whenever you write the notes in this run, set the
   notes' `Saved reports:` line to this SHA.

If a member says it could not write its critique or revision, send it the same message again
once; if it still cannot, stop as in "When you cannot continue".

## 6. Verify

- First review:
  - Merge the members' final reports (the reviewer's and the architect's, revised in step 5)
    and drop duplicates across them.
  - Drop a finding that another reviewer already raised in an existing thread, issue comment
    or review.
  - Check every remaining finding against the code at HEAD; drop what does not hold.
  - A finding is **blocking** when its verified severity is at or above `blocking_threshold`
    (reviewer), or when it is a design defect with a real maintenance consequence (architect).
    Everything else that holds is **non-blocking**. An "investigation needed" item counts only
    if you confirm it.
- Follow-up: check every thread verdict against the code at HEAD; drop what does not hold.
  Settle each checked thread as `addressed`, `partly` or `author-right`, and note whether the
  author's change broke the lines under our comment. Ignore anything a member reports outside
  its threads: a follow-up never raises new issues.

## 7. Draft

Write the body of every comment you will post following `<prompts>/comment-style.md`, in a
few lines each. A follow-up drafts only the findings it posts (`## Unposted`, or a re-review
decision); its replies are written in step 9.

- One issue, one comment: findings about the same issue become one comment; never merge
  different blocking issues.
- Each blocking finding gets its own body. The non-blocking findings become one consolidated
  body, one item per issue.
- Check whether each blocking finding's line is in this run's diff: inside a hunk of
  `git -C <checkout> diff BASE HEAD -- <path>` (side `RIGHT` for a head line, `LEFT` for a
  removed base line). If it is not, the finding is posted file-level, or standalone when it is
  tied to no changed file, so its body starts with the location line
  `<prompts>/comment-style.md` asks for; so does each item of the non-blocking body.
- Permalinks use repository `<repo>` and the full HEAD SHA from step 1:
  `https://github.com/<repo>/blob/<HEAD>/<path>#L<a>-L<b>`.

## 8. Act on GitHub: first review

1. Blocking findings. Anchor each on a line of the diff: a line inside a hunk of
   `git -C <checkout> diff BASE HEAD -- <path>`, side `RIGHT` with its HEAD line number, or
   side `LEFT` with its BASE line number for a removed line. A blocking finding with no diff
   line goes on the most relevant changed file as a file-level comment. Each `body` is its
   step 7 draft. Post them all at once:

   ```bash
   pr-review gh <repo> <PR> post-review --commit <HEAD> <<'EOF'
   {"comments": [{"path": "a.cpp", "line": 12, "side": "RIGHT", "body": "..."},
                 {"path": "b.hpp", "subject_type": "file", "body": "..."}]}
   EOF
   ```

   Line comments go out as one review of type `COMMENT`, each in its own thread. It prints
   `{"thread_ids": [...]}`. Match each new thread to its finding by path, line and body from
   `pr-review gh <repo> <PR> threads`, and record its ID and `url` in the notes.
   If it exits 1 printing `{"error", "review_id", "comment_ids", "thread_ids"}`, part was
   posted: do not post everything again. A non-null `review_id` means every line comment went
   out; `comment_ids` holds the file-level comments posted, in input order. Record what was
   posted (find thread IDs with `threads` if `thread_ids` is null), then post only the missing
   comments.
2. A blocking finding tied to no changed file: its own standalone comment, body on stdin:

   ```bash
   pr-review gh <repo> <PR> comment <<'EOF'
   ...
   EOF
   ```

   Record it in the notes as blocking with thread ID `standalone`.
3. Non-blocking findings: all in one standalone comment, one item per issue, the same way.
   They are not tracked and do not affect approval.
4. First review only: if there are no blocking findings, approve now with
   `pr-review gh <repo> <PR> approve --commit <HEAD>`. If it prints `{"skipped": "own-pr"}`,
   the PR is the user's own: count it as approved anyway. If it prints
   `{"skipped": "head-moved"}`, the author pushed commits we have not reviewed: it did not
   approve, so do not count it as approved, and say so in the notes' log line. The notes
   record the head we reviewed, so the next run follows up on the new commits. In a follow-up,
   never use this item; there the only approval rule is step 9's.

Result: `approved` if you approved, otherwise `reviewed`.

## 9. Act on GitHub: follow-up

Reply with `pr-review gh <repo> <PR> reply <thread-id>` (body on stdin), and change a thread
with `resolve <thread-id>` or `unresolve <thread-id>`. Keep each reply short: follow the tone
and wording rules of `<prompts>/comment-style.md`, not its two-paragraph shape for findings.
Per thread you checked:

- **Addressed:** resolve it with no reply (skip the resolve if it is already resolved); state
  `addressed`.
- **Resolved by the author but not addressed:** unresolve it, reply briefly with what is still
  open; state `partly`.
- **Partly addressed, or the author pushed back.** If the author replied, weigh their reply:
  - the remaining gap is acceptable: resolve with no reply; state `addressed`;
  - the author shows our review was wrong or missed something: reply saying we changed our
    view and why, then resolve; state `accepted-author-view`;
  - otherwise, if the thread is not `disputed` yet, reply once with concrete evidence; state
    `disputed`;
  - otherwise the author still disagrees after our evidence reply: post nothing, escalate
    (below); state `escalated`.
  If the author did not reply, reply once with what is still missing, unless our last reply
  already said it; state `partly`.
- **The author's fix breaks the lines under our comment:** say so in that same thread; state
  `partly`.
- **Nothing changed and no reply:** stay silent.
- A `standalone` blocking item cannot be resolved: update its state in the notes only.

**Substantial new code.** Unless the last reviewed head is `unknown`, list what the PR's own
commits changed since then: `git -C <checkout> range-diff <last base>..<last head> BASE..HEAD`
(if the last head is missing locally, `git -C <checkout> fetch origin <last head>` first).
A change is related when it is in or next to the lines of one of our threads, or is part of
the fix a thread asked for. If the unrelated changes add a file or a function, or exceed
`unrelated_change_lines` changed lines, post nothing new, do not approve, and escalate (below)
with what was added. Never comment on new code in a follow-up.

**A `## Decision` in the notes** is the user's answer to our last escalation. Apply it:
- for a disputed thread: either reply briefly accepting the author's view and resolve it
  (state `accepted-author-view`), or reply once that the requested change still stands and
  leave it open (state `disputed`);
- for substantial new code: "approve" accepts the escalated commits as they are; "re-review"
  means the first-review findings on them from steps 4 and 6 are drafted (step 7) and posted
  as in step 8 items 1-3; approval follows step 9's rule only;
- if the decision is unclear, escalate again quoting it.

**Escalate** by writing the escalation into the notes (thread or new-code range, the author's
position, our position) and reporting `escalated` with one paragraph naming, for each item,
the PR, the thread link (the thread's `url`, as in the notes' Link column; or the commit
range), the author's position and ours.

**Approve** when every blocking thread and standalone item is `addressed` or
`accepted-author-view` and nothing is escalated: `pr-review gh <repo> <PR> approve --commit <HEAD>`
(`{"skipped": "own-pr"}` counts as approved; `{"skipped": "head-moved"}` does not, as in step 8
item 4).

Result: `escalated` if anything was escalated; else `approved` if you approved; else
`reviewed` if you replied, resolved or unresolved anything; else `no-action`.

## 10. Finish

In a preview, the result is never `approved`: a would-be approval was only recorded, so the
result is `reviewed` instead, and never set `Status: approved`.

1. Create or update the notes file (format below): set the last reviewed head and base to
   HEAD and BASE, set `Status:` to this run's result, update every thread's state, and add a
   log line for this run. A first review that saved reports in step 5 sets `Saved reports:` to
   their SHA; a follow-up never changes `Saved reports:`, and saves no reports. If step 9
   handled a `## Decision` (applied it, or escalated again quoting it), copy the decision into
   the entry of the escalation it answered (`Decision applied:`), then remove the `## Decision`
   section, so the next run does not apply it again.
2. Close each member still open: `pr-review member-close <agent>`.
3. If the result is `approved`, or this run is a preview (`--include-merged` on a merged or
   closed PR), delete the PR branch: `pr-review drop-branch <repo> <PR> --checkout <checkout>`.
4. Go to **Report**.

## Report

Every run ends here with exactly one result, and every exit after `lock` succeeded goes through
this section, so the lock is always released.

1. If you hold the lock (step 1 item 5 printed `{"locked": true}`), release it:
   `pr-review unlock <repo> <PR> --holder <holder>`.
2. If this run checked out the PR (step 1 item 9), delete the branches of PRs merged, closed
   or approved since: `pr-review cleanup <repo> --checkout <checkout>`. This step is not fatal:
   whatever it prints or exits with, do not retry it, and do not change the result; go on.
3. With `--supervisor`, send it one message, quoting the text safely as one argument:

   ```bash
   pr-review notify <supervisor> "done <PR> <result> head=<sha|none> dry_run=<true|false> [summary]"
   ```

   - `<result>`: one of the results below.
   - `head=`: HEAD from step 1 (the full SHA) once the PR is checked out; for `no-action` on an
     already-approved head, that head; `head=none` for a run that stopped before the checkout.
   - `dry_run=`: the config's `dry_run` (`true` when the key is absent, and when there is no
     readable config); `true` in a preview.
   - summary: one paragraph on what was done; for `escalated`, the escalation paragraph from
     step 9; for `needs-config`, the problem. In a preview, say that the PR is merged or closed
     and its writes were recorded in `<notes>`, not posted.

   Then do nothing more: the supervisor closes this tab.
4. Without `--supervisor`, tell the user in this session: the result, the head, whether it was
   a dry run (in a dry run the would-be comments are in `<notes>`, under `## Dry run actions`;
   a preview counts as a dry run), and the summary. For `escalated`, also say how to answer:
   `/pr-review <repo> <PR> --decision "<answer>"`.

Results:

- `reviewed`: comments posted, or follow-up replies, resolves or unresolves; not approved.
- `approved`: approved in this run (including `{"skipped": "own-pr"}`).
- `escalated`: something needs the user's decision (step 9).
- `no-action`: nothing to do, including a head already approved.
- `not-interesting`: the spot-check found the PR outside `<interest>`, or only skipped paths
  changed.
- `merged`, `closed`: the PR is finished; its branch was deleted.
- `needs-config`: no usable repository config (only with `--supervisor`).
- `busy`: another run holds this PR's lock.

## Notes file format

```markdown
# PR <PR> notes

## Review state
- Last reviewed head: <sha> (base <sha>) at <UTC time>
- Saved reports: <sha>
- Status: <result>

## Threads
| Thread ID | Link (thread url) | Path:line | Role | Blocking | State |
|---|---|---|---|---|---|

## Escalations
### <thread ID or "new code <sha>..<sha>"> (<UTC date>)
- Author: <their position>
- Ours: <our position>
- Decision applied: <the user's decision, once applied>

## Log
- <UTC time> <mode>: <what was posted, resolved, approved or escalated>
```

States: `open`, `addressed`, `partly`, `disputed`, `escalated`, `accepted-author-view`.

## When you cannot continue

If a command fails, retry it once. If it still fails, or a member cannot finish after its
second task, stop. If anything was posted, record it in the notes, and list the verified
findings not yet posted under `## Unposted` (create no notes file if nothing was posted, so a
retry is a first review again). If you hold the lock, release it:
`pr-review unlock <repo> <PR> --holder <holder>`. If this run checked out the PR, run
`pr-review cleanup <repo> --checkout <checkout>` as in **Report** item 2. Leave the member
panes open so the problem can be inspected. Then print the problem in your pane. With
`--supervisor`, do not report `done`: the supervisor flags the run as stalled and the user
decides. Without it, tell the user the problem.
